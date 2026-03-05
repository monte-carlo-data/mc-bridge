"""Configuration management for MC Bridge.

Config file: ~/.montecarlodata/mc-bridge.yaml

Example:
    connectors:
      my-snowflake:
        account: myaccount.us-east-1
        user: user@company.com
        warehouse: COMPUTE_WH
        database: MY_DB
        schema: PUBLIC
        role: MY_ROLE
"""

import sys
from pathlib import Path

import yaml

from mc_bridge.models import ConnectorConfig

CONFIG_DIR = Path.home() / ".montecarlodata"
CONFIG_FILE = CONFIG_DIR / "mc-bridge.yaml"

EXAMPLE_CONFIG = """\
connectors:
  my-snowflake:
    account: myaccount.us-east-1    # Snowflake account identifier
    user: user@company.com          # Your Snowflake username
    warehouse: COMPUTE_WH           # Warehouse to use
    database: MY_DB                 # (optional) Default database
    schema: PUBLIC                  # (optional) Default schema
    role: MY_ROLE                   # (optional) Role to use

  # Add more connectors as needed:
  # prod-snowflake:
  #   account: prod.us-east-1
  #   user: user@company.com
  #   warehouse: PROD_WH
"""


def print_setup_instructions() -> None:
    """Print configuration instructions and exit."""
    print("\n" + "=" * 60)
    print("MC Bridge - Configuration Required")
    print("=" * 60)
    print(f"\nNo configuration found at: {CONFIG_FILE}")
    print("\nTo get started, create the config file:")
    print(f"\n  mkdir -p {CONFIG_DIR}")
    print(f"  cat > {CONFIG_FILE} << 'EOF'")
    print(EXAMPLE_CONFIG + "EOF")
    print("\nThen run mc-bridge again.")
    print("=" * 60 + "\n")
    sys.exit(1)


class ConfigManager:
    """Manages connector configurations from YAML file."""

    def __init__(self, config_file: Path = CONFIG_FILE) -> None:
        self.config_file = config_file

    def _load_config(self) -> dict:
        """Load config from YAML file."""
        if not self.config_file.exists():
            return {}
        with open(self.config_file) as f:
            return yaml.safe_load(f) or {}

    def has_config(self) -> bool:
        """Check if a valid configuration exists."""
        if not self.config_file.exists():
            return False
        config = self._load_config()
        connectors = config.get("connectors", {})
        return len(connectors) > 0

    def validate_or_exit(self) -> None:
        """Validate config exists or print instructions and exit."""
        if not self.has_config():
            print_setup_instructions()

    def list_connectors(self) -> list[ConnectorConfig]:
        """List all connectors."""
        config = self._load_config()
        connectors_dict = config.get("connectors", {})

        connectors = []
        for connector_id, connector_data in connectors_dict.items():
            connectors.append(
                ConnectorConfig(
                    id=connector_id,
                    name=connector_data.get("name", connector_id),
                    account=connector_data["account"],
                    user=connector_data["user"],
                    warehouse=connector_data["warehouse"],
                    database=connector_data.get("database"),
                    schema_name=connector_data.get("schema"),
                    role=connector_data.get("role"),
                )
            )
        return connectors

    def get_connector(self, connector_id: str) -> ConnectorConfig | None:
        """Get a connector by ID."""
        for c in self.list_connectors():
            if c.id == connector_id:
                return c
        return None


# Global config manager instance
config_manager = ConfigManager()

