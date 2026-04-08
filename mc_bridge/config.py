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

      my-bigquery:
        type: bigquery
        project: my-gcp-project
        dataset: my_dataset

      my-redshift:
        type: redshift
        host: my-cluster.us-east-1.redshift.amazonaws.com
        user: admin
        database: mydb
        password: mypassword
"""

import sys
from pathlib import Path
from typing import Union

import yaml

from mc_bridge.models import (
    BigQueryConnectorConfig,
    RedshiftConnectorConfig,
    SnowflakeConnectorConfig,
)

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
    # method: externalbrowser       # (default) Opens browser for SSO
    # method: password              # Requires: password field
    # method: keypair               # Requires: private_key_path (or private_key)

  # my-bigquery:
  #   type: bigquery
  #   project: my-gcp-project       # GCP project ID
  #   dataset: my_dataset           # (optional) Default dataset
  #   location: US                  # (optional) US or EU
  #   # method: oauth               # (default) Uses gcloud auth application-default login
  #   # method: service-account     # Requires: keyfile

  # my-redshift:
  #   type: redshift
  #   host: cluster.region.redshift.amazonaws.com
  #   user: admin
  #   database: mydb
  #   password: mypassword
  #   schema: public                # (optional)
  #   # method: database            # (default) User/password
  #   # method: iam                 # Uses AWS credential chain
"""

_SUPPORTED_DBT_TYPES = {"snowflake", "bigquery", "redshift"}

AnyConnectorConfig = Union[
    SnowflakeConnectorConfig, BigQueryConnectorConfig, RedshiftConnectorConfig
]


def _infer_connector_type(connector_data: dict) -> str:
    """Infer connector type from fields. Defaults to snowflake for backwards compat."""
    if "type" in connector_data:
        return connector_data["type"]
    if "project" in connector_data:
        return "bigquery"
    if "host" in connector_data:
        return "redshift"
    return "snowflake"


def _build_snowflake_config(connector_id: str, data: dict) -> SnowflakeConnectorConfig:
    return SnowflakeConnectorConfig(
        id=connector_id,
        name=data.get("name", connector_id),
        account=data["account"],
        user=data["user"],
        warehouse=data["warehouse"],
        database=data.get("database"),
        schema_name=data.get("schema"),
        role=data.get("role"),
        method=data.get("method", "externalbrowser"),
        password=data.get("password"),
        private_key=data.get("private_key"),
        private_key_path=data.get("private_key_path"),
        private_key_passphrase=data.get("private_key_passphrase"),
    )


def _build_bigquery_config(connector_id: str, data: dict) -> BigQueryConnectorConfig:
    return BigQueryConnectorConfig(
        id=connector_id,
        name=data.get("name", connector_id),
        project=data["project"],
        dataset=data.get("dataset"),
        schema_name=data.get("schema"),
        method=data.get("method", "oauth"),
        keyfile=data.get("keyfile"),
        location=data.get("location"),
        job_execution_timeout_seconds=data.get("job_execution_timeout_seconds", 300),
        maximum_bytes_billed=data.get("maximum_bytes_billed"),
    )


def _build_redshift_config(connector_id: str, data: dict) -> RedshiftConnectorConfig:
    return RedshiftConnectorConfig(
        id=connector_id,
        name=data.get("name", connector_id),
        host=data["host"],
        port=data.get("port", 5439),
        user=data["user"],
        database=data.get("database", data.get("dbname", "")),
        schema_name=data.get("schema"),
        method=data.get("method", "database"),
        password=data.get("password", data.get("pass")),
        iam_profile=data.get("iam_profile"),
        cluster_id=data.get("cluster_id"),
        region=data.get("region"),
        connect_timeout=data.get("connect_timeout"),
        role=data.get("role"),
        sslmode=data.get("sslmode"),
    )


_CONFIG_BUILDERS: dict[str, callable] = {
    "snowflake": _build_snowflake_config,
    "bigquery": _build_bigquery_config,
    "redshift": _build_redshift_config,
}


def _parse_dbt_profiles() -> dict[str, dict] | None:
    """Parse dbt profiles.yml and extract connection configs for supported types.

    Returns a dict mapping connector_id -> connector config dict,
    or None if no supported targets found.
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

            target_type = target_config.get("type")
            if target_type not in _SUPPORTED_DBT_TYPES:
                continue

            connector_id = f"{profile_name}-{target_name}"
            # Copy all fields except type and threads, add type back explicitly
            connector: dict = {"type": target_type}
            connector.update(
                {k: v for k, v in target_config.items() if k not in ("type", "threads")}
            )
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

    type_counts: dict[str, int] = {}
    for cfg in dbt_connectors.values():
        t = cfg.get("type", "snowflake")
        type_counts[t] = type_counts.get(t, 0) + 1

    summary = ", ".join(f"{count} {t}" for t, count in type_counts.items())
    print(f"\nFound {len(dbt_connectors)} connection(s) in {DBT_PROFILES_FILE} ({summary}):")
    for name, cfg in dbt_connectors.items():
        print(f"  - {name} (type: {cfg.get('type', 'snowflake')})")

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

    print(f"\nTo get started, create the config file at:\n  {CONFIG_FILE}")
    if sys.platform == "win32":
        print(f'\n  mkdir "{CONFIG_DIR}"')
        print(f'  notepad "{CONFIG_FILE}"')
    else:
        print(f"\n  mkdir -p {CONFIG_DIR}")
        print(f"  cat > {CONFIG_FILE} << 'EOF'")
        print(EXAMPLE_CONFIG + "EOF")
    print("\nExample config:\n")
    print(EXAMPLE_CONFIG)
    print("Then run mc-bridge again.")
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

    def list_connectors(self) -> list[AnyConnectorConfig]:
        """List all connectors."""
        config = self._load_config()
        connectors_dict = config.get("connectors", {})

        connectors: list[AnyConnectorConfig] = []
        for connector_id, connector_data in connectors_dict.items():
            connector_type = _infer_connector_type(connector_data)
            builder = _CONFIG_BUILDERS.get(connector_type)
            if builder is None:
                continue
            connectors.append(builder(connector_id, connector_data))
        return connectors

    def get_connector(self, connector_id: str) -> AnyConnectorConfig | None:
        """Get a connector by ID."""
        for c in self.list_connectors():
            if c.id == connector_id:
                return c
        return None


# Global config manager instance
config_manager = ConfigManager()
