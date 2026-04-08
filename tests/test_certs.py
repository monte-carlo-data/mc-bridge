"""Tests for certificate generation and management."""

import datetime
import ipaddress
import stat
import subprocess
import sys
from unittest.mock import MagicMock, patch

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
    _install_ca_linux,
    _install_ca_macos,
    _install_ca_windows,
    _is_ca_trusted_macos,
    _is_ca_trusted_windows,
    _is_cert_expiring_soon,
    _load_ca,
    ca_trust_guidance,
    ensure_certificates,
    install_ca_to_system_trust,
    is_ca_trusted,
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


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not available on Windows")
def test_file_permissions(certs_dir):
    """Key files have restrictive permissions."""
    _generate_ca()

    ca_key_mode = (certs_dir / CA_KEY_FILE).stat().st_mode
    assert stat.S_IMODE(ca_key_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions not available on Windows")
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


# --- Cross-platform cert trust tests ---


def test_install_ca_macos_success(tmp_path):
    """macOS install calls security add-trusted-cert."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _install_ca_macos(cert_path)

    assert result is True
    args = mock_run.call_args[0][0]
    assert args[0] == "security"
    assert "add-trusted-cert" in args


def test_install_ca_macos_failure(tmp_path):
    """macOS install returns False on CalledProcessError."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "security", stderr="denied")
        result = _install_ca_macos(cert_path)

    assert result is False


def test_install_ca_windows_success(tmp_path):
    """Windows install calls certutil -addstore Root."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _install_ca_windows(cert_path)

    assert result is True
    args = mock_run.call_args[0][0]
    assert args == ["certutil", "-addstore", "Root", str(cert_path)]


def test_install_ca_windows_failure(tmp_path):
    """Windows install returns False when certutil fails (e.g., not admin)."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "certutil", stderr="access denied")
        result = _install_ca_windows(cert_path)

    assert result is False


def test_install_ca_linux_returns_false(tmp_path):
    """Linux install always returns False (prints instructions only)."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")
    result = _install_ca_linux(cert_path)
    assert result is False


def test_is_ca_trusted_macos_success(tmp_path):
    """macOS trust check returns True when security verify-cert succeeds."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _is_ca_trusted_macos(cert_path)

    assert result is True


def test_is_ca_trusted_macos_failure(tmp_path):
    """macOS trust check returns False when security verify-cert fails."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "security")
        result = _is_ca_trusted_macos(cert_path)

    assert result is False


def test_is_ca_trusted_windows_found(tmp_path):
    """Windows trust check returns True when certutil finds the cert."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = _is_ca_trusted_windows(cert_path)

    assert result is True
    args = mock_run.call_args[0][0]
    assert args == ["certutil", "-store", "Root", "MC Bridge Local CA"]


def test_is_ca_trusted_windows_not_found(tmp_path):
    """Windows trust check returns False when cert not in store."""
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        result = _is_ca_trusted_windows(cert_path)

    assert result is False


def test_install_ca_dispatches_to_macos(tmp_path, monkeypatch):
    """install_ca_to_system_trust dispatches to macOS on darwin."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "darwin")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs._install_ca_macos", return_value=True) as mock:
        result = install_ca_to_system_trust(cert_path)

    assert result is True
    mock.assert_called_once_with(cert_path)


def test_install_ca_dispatches_to_windows(tmp_path, monkeypatch):
    """install_ca_to_system_trust dispatches to Windows on win32."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "win32")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", True)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs._install_ca_windows", return_value=True) as mock:
        result = install_ca_to_system_trust(cert_path)

    assert result is True
    mock.assert_called_once_with(cert_path)


def test_install_ca_dispatches_to_linux(tmp_path, monkeypatch):
    """install_ca_to_system_trust dispatches to Linux on linux."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "linux")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs._install_ca_linux", return_value=False) as mock:
        result = install_ca_to_system_trust(cert_path)

    assert result is False
    mock.assert_called_once_with(cert_path)


def test_is_ca_trusted_dispatches_to_macos(tmp_path, monkeypatch):
    """is_ca_trusted dispatches to macOS on darwin."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "darwin")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs._is_ca_trusted_macos", return_value=True) as mock:
        result = is_ca_trusted(cert_path)

    assert result is True
    mock.assert_called_once_with(cert_path)


def test_is_ca_trusted_dispatches_to_windows(tmp_path, monkeypatch):
    """is_ca_trusted dispatches to Windows on win32."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "win32")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", True)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    with patch("mc_bridge.certs._is_ca_trusted_windows", return_value=True) as mock:
        result = is_ca_trusted(cert_path)

    assert result is True
    mock.assert_called_once_with(cert_path)


def test_is_ca_trusted_linux_returns_false(tmp_path, monkeypatch):
    """is_ca_trusted returns False on Linux (no automated check)."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "linux")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    cert_path = tmp_path / "ca.pem"
    cert_path.write_text("fake cert")

    result = is_ca_trusted(cert_path)
    assert result is False


def test_is_ca_trusted_missing_file(tmp_path):
    """is_ca_trusted returns False when cert file doesn't exist."""
    result = is_ca_trusted(tmp_path / "nonexistent.pem")
    assert result is False


def test_ca_trust_guidance_macos(tmp_path, monkeypatch):
    """Guidance for macOS references security add-trusted-cert."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "darwin")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    guidance = ca_trust_guidance(tmp_path / "ca.pem")
    assert "security add-trusted-cert" in guidance


def test_ca_trust_guidance_windows(tmp_path, monkeypatch):
    """Guidance for Windows references certutil."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "win32")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", True)
    guidance = ca_trust_guidance(tmp_path / "ca.pem")
    assert "certutil -addstore Root" in guidance


def test_ca_trust_guidance_linux(tmp_path, monkeypatch):
    """Guidance for Linux references update-ca-certificates."""
    monkeypatch.setattr("mc_bridge.certs.sys.platform", "linux")
    monkeypatch.setattr("mc_bridge.certs.IS_WINDOWS", False)
    guidance = ca_trust_guidance(tmp_path / "ca.pem")
    assert "update-ca-certificates" in guidance
