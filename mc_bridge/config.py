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

from pathlib import Path

import yaml

from mc_bridge.models import ConnectorConfig

CONFIG_FILE = Path.home() / ".montecarlodata" / "mc-bridge.yaml"


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

