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
DBT_PROFILES_FILE = Path.home() / ".dbt" / "profiles.yml"

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


def _parse_dbt_profiles() -> dict[str, dict] | None:
    """Parse dbt profiles.yml and extract Snowflake connection configs.

    Returns a dict mapping connector_id -> connector config dict,
    or None if no Snowflake targets found.
    """
    if not DBT_PROFILES_FILE.exists():
        return None

    with open(DBT_PROFILES_FILE) as f:
        profiles = yaml.safe_load(f) or {}

    connectors: dict[str, dict] = {}
    for profile_name, profile_data in profiles.items():
        if not isinstance(profile_data, dict) or "outputs" not in profile_data:
            continue

        outputs = profile_data["outputs"]
        if not isinstance(outputs, dict):
            continue

        for target_name, target_config in outputs.items():
            if not isinstance(target_config, dict):
                continue
            if target_config.get("type") != "snowflake":
                continue

            # Required fields for mc-bridge
            account = target_config.get("account")
            user = target_config.get("user")
            warehouse = target_config.get("warehouse")
            if not all([account, user, warehouse]):
                continue

            connector_id = f"{profile_name}-{target_name}"
            connector: dict[str, str] = {
                "account": account,
                "user": user,
                "warehouse": warehouse,
            }

            if target_config.get("database"):
                connector["database"] = target_config["database"]
            if target_config.get("schema"):
                connector["schema"] = target_config["schema"]
            if target_config.get("role"):
                connector["role"] = target_config["role"]

            connectors[connector_id] = connector

    return connectors if connectors else None


def _write_config_from_dbt(connectors: dict[str, dict]) -> None:
    """Write mc-bridge config file from parsed dbt connectors."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {"connectors": connectors}
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def _prompt_dbt_import() -> bool:
    """Prompt user to import from dbt profiles. Returns True if config was created."""
    dbt_connectors = _parse_dbt_profiles()
    if not dbt_connectors:
        return False

    print(f"\nFound {len(dbt_connectors)} Snowflake connection(s) in {DBT_PROFILES_FILE}:")
    for name, cfg in dbt_connectors.items():
        print(f"  - {name} ({cfg['account']}, user: {cfg['user']})")

    try:
        answer = input("\nImport these connections? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer in ("", "y", "yes"):
        _write_config_from_dbt(dbt_connectors)
        print(f"\nConfig written to {CONFIG_FILE}")
        return True
    return False


def print_setup_instructions() -> None:
    """Print configuration instructions and exit. Offers dbt import if available."""
    print("\n" + "=" * 60)
    print("MC Bridge - Configuration Required")
    print("=" * 60)
    print(f"\nNo configuration found at: {CONFIG_FILE}")

    # Offer dbt import if profiles.yml exists
    if _prompt_dbt_import():
        print("=" * 60 + "\n")
        return

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

