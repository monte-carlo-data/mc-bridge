"""JWT authentication for MC Bridge.

Validates RS256 JWTs signed by the MC backend. Supports key rotation by bundling
current + next public keys and trying each in order.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)

KEYS_DIR = Path(__file__).parent / "keys"

EXPECTED_AUDIENCE = "mc-bridge"
EXPECTED_ISSUER = "monte-carlo"


@dataclass
class TokenClaims:
    """Validated JWT claims."""

    sub: str
    exp: int
    aud: str
    iss: str


def load_public_keys() -> list:
    """Load current + next public keys from bundled keys directory.

    Tries current.pem first, then next.pem for rotation support.
    Returns list of RSA public key objects.
    """
    keys = []
    for filename in ("current.pem", "next.pem"):
        key_path = KEYS_DIR / filename
        if key_path.exists():
            pem_data = key_path.read_bytes()
            keys.append(load_pem_public_key(pem_data))
    return keys


def validate_token(token: str) -> TokenClaims:
    """Validate a JWT token and return claims.

    Tries each bundled public key in order. Validates:
    - RS256 signature
    - aud == "mc-bridge"
    - iss == "monte-carlo"
    - exp not past
    - sub is non-empty

    Raises jwt.InvalidTokenError on failure.
    """
    keys = load_public_keys()
    if not keys:
        raise jwt.InvalidTokenError("No public keys configured")

    last_error: Exception | None = None
    for key in keys:
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=EXPECTED_AUDIENCE,
                issuer=EXPECTED_ISSUER,
            )
            sub = payload.get("sub", "")
            if not sub:
                raise jwt.InvalidTokenError("Missing 'sub' claim")
            return TokenClaims(
                sub=sub,
                exp=payload["exp"],
                aud=payload["aud"],
                iss=payload["iss"],
            )
        except jwt.InvalidTokenError as e:
            last_error = e
            continue

    raise last_error  # type: ignore[misc]
