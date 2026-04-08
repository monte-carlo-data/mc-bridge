"""Certificate generation and management for MC Bridge HTTPS."""

import datetime
import ipaddress
import logging
import subprocess
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

CERTS_DIR = Path.home() / ".montecarlodata" / "certs"

CA_CERT_FILE = "ca.pem"
CA_KEY_FILE = "ca-key.pem"
SERVER_CERT_FILE = "server.pem"
SERVER_KEY_FILE = "server-key.pem"

CA_VALIDITY_YEARS = 10
SERVER_VALIDITY_YEARS = 1
RENEWAL_THRESHOLD_DAYS = 30

IS_WINDOWS = sys.platform == "win32"


def _secure_mkdir(path: Path) -> None:
    """Create directory with restrictive permissions (no-op for mode on Windows)."""
    if IS_WINDOWS:
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)


def _secure_chmod(path: Path, mode: int) -> None:
    """Set file permissions (no-op on Windows — relies on NTFS user-private dirs)."""
    if not IS_WINDOWS:
        path.chmod(mode)


def ensure_certificates() -> tuple[Path, Path, Path]:
    """Ensure valid CA + server certs exist. Returns (ca_cert, server_cert, server_key).

    Creates CERTS_DIR if missing. Generates root CA (10yr validity)
    if ca.pem/ca-key.pem missing. Generates server cert (1yr validity, SAN: localhost
    + 127.0.0.1) if missing or expiring within 30 days.
    """
    _secure_mkdir(CERTS_DIR)

    ca_cert_path = CERTS_DIR / CA_CERT_FILE
    ca_key_path = CERTS_DIR / CA_KEY_FILE
    server_cert_path = CERTS_DIR / SERVER_CERT_FILE
    server_key_path = CERTS_DIR / SERVER_KEY_FILE

    # Generate CA if missing
    if not ca_cert_path.exists() or not ca_key_path.exists():
        logger.info("Generating root CA certificate")
        _generate_ca()

    ca_cert, ca_key = _load_ca()

    # Generate server cert if missing or expiring soon
    if (
        not server_cert_path.exists()
        or not server_key_path.exists()
        or _is_cert_expiring_soon(server_cert_path, RENEWAL_THRESHOLD_DAYS)
    ):
        logger.info("Generating server certificate")
        _generate_server_cert(ca_cert, ca_key)

    return ca_cert_path, server_cert_path, server_key_path


def _generate_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate root CA cert + key. Write to CERTS_DIR/ca.pem, ca-key.pem."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "MC Bridge Local CA"),
        ]
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=CA_VALIDITY_YEARS * 365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    ca_key_path = CERTS_DIR / CA_KEY_FILE
    ca_cert_path = CERTS_DIR / CA_CERT_FILE

    ca_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    _secure_chmod(ca_key_path, 0o600)

    ca_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert, key


def _generate_server_cert(
    ca_cert: x509.Certificate, ca_key: rsa.RSAPrivateKey
) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Generate server cert signed by CA. SAN: localhost, 127.0.0.1."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=SERVER_VALIDITY_YEARS * 365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    server_key_path = CERTS_DIR / SERVER_KEY_FILE
    server_cert_path = CERTS_DIR / SERVER_CERT_FILE

    server_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    _secure_chmod(server_key_path, 0o600)

    server_cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert, key


def _is_cert_expiring_soon(cert_path: Path, days: int = 30) -> bool:
    """Check if cert expires within `days`."""
    cert_data = cert_path.read_bytes()
    cert = x509.load_pem_x509_certificate(cert_data)
    threshold = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)
    return cert.not_valid_after_utc < threshold


def _load_ca() -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Load existing CA cert + key from disk."""
    ca_cert_path = CERTS_DIR / CA_CERT_FILE
    ca_key_path = CERTS_DIR / CA_KEY_FILE

    cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)

    return cert, key  # type: ignore[return-value]


def install_ca_to_system_trust(ca_cert_path: Path) -> bool:
    """Install CA cert into the OS trust store.

    macOS: security add-trusted-cert (login keychain)
    Windows: certutil -addstore Root (may need admin)
    Linux: prints manual instructions (needs sudo)

    Returns True on success, False on failure.
    """
    if sys.platform == "darwin":
        return _install_ca_macos(ca_cert_path)
    elif IS_WINDOWS:
        return _install_ca_windows(ca_cert_path)
    else:
        return _install_ca_linux(ca_cert_path)


def _install_ca_macos(ca_cert_path: Path) -> bool:
    try:
        subprocess.run(
            [
                "security",
                "add-trusted-cert",
                "-r",
                "trustRoot",
                "-k",
                str(Path.home() / "Library" / "Keychains" / "login.keychain-db"),
                str(ca_cert_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("CA certificate installed to macOS login keychain")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("Failed to install CA certificate: %s", e.stderr)
        return False


def _install_ca_windows(ca_cert_path: Path) -> bool:
    try:
        subprocess.run(
            ["certutil", "-addstore", "Root", str(ca_cert_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("CA certificate installed to Windows Root store")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("Failed to install CA certificate: %s", e.stderr)
        logger.warning(
            "Try running as Administrator, or manually: certutil -addstore Root %s",
            ca_cert_path,
        )
        return False


def _install_ca_linux(ca_cert_path: Path) -> bool:
    logger.warning(
        "Automatic CA install not supported on Linux. To trust the CA, run:\n"
        "  sudo cp %s /usr/local/share/ca-certificates/mc-bridge-ca.crt\n"
        "  sudo update-ca-certificates",
        ca_cert_path,
    )
    return False


def is_ca_trusted(ca_cert_path: Path) -> bool:
    """Check if the CA is trusted in the OS trust store."""
    if not ca_cert_path.exists():
        return False
    if sys.platform == "darwin":
        return _is_ca_trusted_macos(ca_cert_path)
    elif IS_WINDOWS:
        return _is_ca_trusted_windows(ca_cert_path)
    else:
        # No reliable automated check on Linux
        return False


def _is_ca_trusted_macos(ca_cert_path: Path) -> bool:
    try:
        subprocess.run(
            ["security", "verify-cert", "-c", str(ca_cert_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _is_ca_trusted_windows(ca_cert_path: Path) -> bool:
    """Check if CA is in the Windows Root store by matching subject CN."""
    try:
        result = subprocess.run(
            ["certutil", "-store", "Root", "MC Bridge Local CA"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def ca_trust_guidance(ca_cert_path: Path) -> str:
    """Return platform-specific instructions for manually trusting the CA."""
    if sys.platform == "darwin":
        return (
            "CA certificate is not trusted. Run: "
            "security add-trusted-cert -r trustRoot "
            f"-k ~/Library/Keychains/login.keychain-db {ca_cert_path}"
        )
    elif IS_WINDOWS:
        return (
            "CA certificate is not trusted. Run (as Administrator): "
            f"certutil -addstore Root {ca_cert_path}"
        )
    else:
        return (
            "CA certificate is not trusted. Run:\n"
            f"  sudo cp {ca_cert_path} /usr/local/share/ca-certificates/mc-bridge-ca.crt\n"
            "  sudo update-ca-certificates"
        )
