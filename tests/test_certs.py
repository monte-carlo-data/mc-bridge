"""Tests for certificate generation and management."""

import datetime
import ipaddress
import stat

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from mc_bridge.certs import (
    CA_CERT_FILE,
    CA_KEY_FILE,
    SERVER_CERT_FILE,
    SERVER_KEY_FILE,
    _generate_ca,
    _generate_server_cert,
    _is_cert_expiring_soon,
    _load_ca,
    ensure_certificates,
)


@pytest.fixture
def certs_dir(tmp_path, monkeypatch):
    """Override CERTS_DIR to use a temporary directory."""
    monkeypatch.setattr("mc_bridge.certs.CERTS_DIR", tmp_path)
    return tmp_path


def test_generate_ca(certs_dir):
    """CA generation creates valid cert + key files."""
    cert, key = _generate_ca()

    assert (certs_dir / CA_CERT_FILE).exists()
    assert (certs_dir / CA_KEY_FILE).exists()

    # Verify CA properties
    assert cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value == (
        "MC Bridge Local CA"
    )
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.value.ca is True

    # Verify self-signed
    assert cert.issuer == cert.subject


def test_generate_server_cert(certs_dir):
    """Server cert is signed by CA and has correct SAN."""
    ca_cert, ca_key = _generate_ca()
    server_cert, server_key = _generate_server_cert(ca_cert, ca_key)

    assert (certs_dir / SERVER_CERT_FILE).exists()
    assert (certs_dir / SERVER_KEY_FILE).exists()

    # Verify signed by CA
    assert server_cert.issuer == ca_cert.subject

    # Verify SAN
    san = server_cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    dns_names = san.value.get_values_for_type(x509.DNSName)
    ip_addresses = san.value.get_values_for_type(x509.IPAddress)
    assert "localhost" in dns_names
    assert ipaddress.IPv4Address("127.0.0.1") in ip_addresses

    # Not a CA
    bc = server_cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.value.ca is False


def test_file_permissions(certs_dir):
    """Key files have restrictive permissions."""
    _generate_ca()

    ca_key_mode = (certs_dir / CA_KEY_FILE).stat().st_mode
    assert stat.S_IMODE(ca_key_mode) == 0o600


def test_ensure_certificates_creates_dir(tmp_path, monkeypatch):
    """ensure_certificates creates the certs directory if missing."""
    certs_dir = tmp_path / "new_certs"
    monkeypatch.setattr("mc_bridge.certs.CERTS_DIR", certs_dir)

    ca_cert, server_cert, server_key = ensure_certificates()

    assert certs_dir.exists()
    assert stat.S_IMODE(certs_dir.stat().st_mode) == 0o700
    assert ca_cert.exists()
    assert server_cert.exists()
    assert server_key.exists()


def test_ensure_certificates_idempotent(certs_dir):
    """Calling ensure_certificates twice doesn't regenerate valid certs."""
    ca1, srv1, key1 = ensure_certificates()

    # Read cert serial numbers
    cert1 = x509.load_pem_x509_certificate(srv1.read_bytes())
    serial1 = cert1.serial_number

    ca2, srv2, key2 = ensure_certificates()
    cert2 = x509.load_pem_x509_certificate(srv2.read_bytes())
    serial2 = cert2.serial_number

    # Same cert, not regenerated
    assert serial1 == serial2


def test_auto_renewal_when_expiring(certs_dir):
    """Server cert is regenerated when expiring within threshold."""
    ensure_certificates()

    # Manually create an almost-expired server cert
    ca_cert, ca_key = _load_ca()
    from cryptography.hazmat.primitives.asymmetric import rsa as rsa_mod

    key = rsa_mod.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    # Expires in 10 days (below 30 day threshold)
    expiring_cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=355))
        .not_valid_after(now + datetime.timedelta(days=10))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_cert_path = certs_dir / SERVER_CERT_FILE
    server_cert_path.write_bytes(expiring_cert.public_bytes(serialization.Encoding.PEM))
    old_serial = expiring_cert.serial_number

    # Should regenerate
    ensure_certificates()

    new_cert = x509.load_pem_x509_certificate(server_cert_path.read_bytes())
    assert new_cert.serial_number != old_serial


def test_is_cert_expiring_soon(certs_dir):
    """_is_cert_expiring_soon correctly detects near-expiry certs."""
    _generate_ca()
    ca_cert_path = certs_dir / CA_CERT_FILE

    # CA has 10 year validity, should not be expiring
    assert _is_cert_expiring_soon(ca_cert_path, days=30) is False
    # But would be "expiring" if threshold is huge
    assert _is_cert_expiring_soon(ca_cert_path, days=365 * 11) is True
