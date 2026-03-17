"""Tests for JWT authentication."""

import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mc_bridge.auth import EXPECTED_AUDIENCE, EXPECTED_ISSUER, TokenClaims, validate_token


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Generate an RSA keypair for testing. Returns (private_key, public_key_pem)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key_pem


@pytest.fixture
def alt_rsa_keypair() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Generate a second RSA keypair (for wrong-key tests)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key_pem


@pytest.fixture
def keys_dir(tmp_path: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> Path:
    """Create a temp keys directory with current.pem."""
    keys = tmp_path / "keys"
    keys.mkdir()
    keys.joinpath("current.pem").write_bytes(rsa_keypair[1])
    return keys


def _make_token(
    private_key: rsa.RSAPrivateKey,
    sub: str = "user-123",
    aud: str = EXPECTED_AUDIENCE,
    iss: str = EXPECTED_ISSUER,
    exp: int | None = None,
) -> str:
    """Helper to create a signed JWT."""
    if exp is None:
        exp = int(time.time()) + 3600
    payload = {"sub": sub, "aud": aud, "iss": iss, "exp": exp}
    return jwt.encode(payload, private_key, algorithm="RS256")


def test_valid_token(keys_dir: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Valid token returns correct claims."""
    private_key, _ = rsa_keypair
    token = _make_token(private_key)

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        claims = validate_token(token)

    assert isinstance(claims, TokenClaims)
    assert claims.sub == "user-123"
    assert claims.aud == EXPECTED_AUDIENCE
    assert claims.iss == EXPECTED_ISSUER


def test_expired_token(keys_dir: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Expired token raises InvalidTokenError."""
    private_key, _ = rsa_keypair
    token = _make_token(private_key, exp=int(time.time()) - 100)

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)


def test_bad_signature(keys_dir: Path, alt_rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Token signed with wrong key raises InvalidTokenError."""
    wrong_key, _ = alt_rsa_keypair
    token = _make_token(wrong_key)

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)


def test_wrong_audience(keys_dir: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Token with wrong audience raises InvalidTokenError."""
    private_key, _ = rsa_keypair
    token = _make_token(private_key, aud="wrong-audience")

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)


def test_wrong_issuer(keys_dir: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Token with wrong issuer raises InvalidTokenError."""
    private_key, _ = rsa_keypair
    token = _make_token(private_key, iss="wrong-issuer")

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        with pytest.raises(jwt.InvalidTokenError):
            validate_token(token)


def test_missing_sub(keys_dir: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """Token with empty sub raises InvalidTokenError."""
    private_key, _ = rsa_keypair
    token = _make_token(private_key, sub="")

    with patch("mc_bridge.auth.KEYS_DIR", keys_dir):
        with pytest.raises(jwt.InvalidTokenError, match="Missing 'sub' claim"):
            validate_token(token)


def test_no_keys_configured(tmp_path: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> None:
    """No public keys raises InvalidTokenError."""
    empty_keys = tmp_path / "empty_keys"
    empty_keys.mkdir()
    private_key, _ = rsa_keypair
    token = _make_token(private_key)

    with patch("mc_bridge.auth.KEYS_DIR", empty_keys):
        with pytest.raises(jwt.InvalidTokenError, match="No public keys configured"):
            validate_token(token)


def test_multiple_keys_rotation(
    tmp_path: Path,
    rsa_keypair: tuple[rsa.RSAPrivateKey, bytes],
    alt_rsa_keypair: tuple[rsa.RSAPrivateKey, bytes],
) -> None:
    """Token signed with next.pem key succeeds when current.pem is different."""
    _, old_pub_pem = rsa_keypair
    new_private, new_pub_pem = alt_rsa_keypair

    keys = tmp_path / "keys"
    keys.mkdir()
    keys.joinpath("current.pem").write_bytes(old_pub_pem)
    keys.joinpath("next.pem").write_bytes(new_pub_pem)

    # Sign with the "next" key
    token = _make_token(new_private)

    with patch("mc_bridge.auth.KEYS_DIR", keys):
        claims = validate_token(token)

    assert claims.sub == "user-123"
