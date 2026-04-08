"""Main entry point for MC Bridge — console server."""

import sys
from pathlib import Path

import uvicorn

from mc_bridge import __version__
from mc_bridge.certs import (
    CERTS_DIR,
    ensure_certificates,
    install_ca_to_system_trust,
    is_ca_trusted,
)

# Default server configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def _prompt_https_setup(ca_cert_path: Path, needs_ca_install: bool) -> bool:
    """Prompt user before HTTPS certificate setup. Returns True if user confirmed."""
    url = f"https://{DEFAULT_HOST}:{DEFAULT_PORT}"
    print("\nMC Bridge uses HTTPS with a local Certificate Authority (CA).")
    print("On first run, this will:")
    print(f"  - Generate a root CA and server certificate in {CERTS_DIR}/")
    if needs_ca_install:
        print("  - Install the CA to your system trust store (may prompt for password)")
    print(f"\nThis allows your browser to trust {url} without warnings.")

    try:
        answer = input("\nProceed? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    return answer in ("", "y", "yes")


def main() -> None:
    """Run the MC Bridge HTTPS server."""
    from mc_bridge.config import config_manager
    from mc_bridge.server import app

    # Validate config exists before starting
    config_manager.validate_or_exit()

    ca_cert_path = CERTS_DIR / "ca.pem"
    needs_generate = not ca_cert_path.exists()
    needs_ca_install = needs_generate or not is_ca_trusted(ca_cert_path)

    if needs_generate or needs_ca_install:
        if not _prompt_https_setup(ca_cert_path, needs_ca_install):
            print("Aborted.")
            sys.exit(0)

    ca_cert, server_cert, server_key = ensure_certificates()

    if not is_ca_trusted(ca_cert):
        install_ca_to_system_trust(ca_cert)

    print(f"\nMC Bridge v{__version__}")
    print(f"Starting server on https://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print("Press Ctrl+C to stop")

    uvicorn.run(
        app,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        log_level="info",
        ssl_keyfile=str(server_key),
        ssl_certfile=str(server_cert),
    )


if __name__ == "__main__":
    main()
