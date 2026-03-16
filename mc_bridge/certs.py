"""Certificate generation and management for MC Bridge HTTPS."""

import datetime
import ipaddress
import logging
import subprocess
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


def ensure_certificates() -> tuple[Path, Path, Path]:
    """Ensure valid CA + server certs exist. Returns (ca_cert, server_cert, server_key).

    Creates CERTS_DIR with mode 0o700 if missing. Generates root CA (10yr validity)
    if ca.pem/ca-key.pem missing. Generates server cert (1yr validity, SAN: localhost
    + 127.0.0.1) if missing or expiring within 30 days.
    """
    CERTS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)

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
    ca_key_path.chmod(0o600)

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
    server_key_path.chmod(0o600)

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
    """Install CA in macOS login keychain via `security add-trusted-cert`.

    Returns True on success, False on failure (user cancelled password prompt).
    """
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


def is_ca_trusted(ca_cert_path: Path) -> bool:
    """Check if CA is already trusted in macOS keychain via `security verify-cert`."""
    if not ca_cert_path.exists():
        return False
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
