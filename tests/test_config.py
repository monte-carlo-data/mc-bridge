"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from mc_bridge.config import ConfigManager
from mc_bridge.models import (
    BigQueryConnectorConfig,
    RedshiftConnectorConfig,
    SnowflakeConnectorConfig,
)


@pytest.fixture
def temp_config_file() -> Path:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def config_manager(temp_config_file: Path) -> ConfigManager:
    """Create a ConfigManager with temporary storage."""
    return ConfigManager(config_file=temp_config_file)


# --- Backwards compatibility tests ---


def test_list_connectors_empty(config_manager: ConfigManager) -> None:
    """Test listing connectors when config file doesn't exist."""
    connectors = config_manager.list_connectors()
    assert connectors == []


def test_snowflake_config_without_type(temp_config_file: Path) -> None:
    """Configs without type field default to snowflake (backwards compat)."""
    temp_config_file.write_text("""
connectors:
  my-snowflake:
    account: test-account.us-east-1
    user: test@example.com
    warehouse: COMPUTE_WH
    database: TEST_DB
    schema: PUBLIC
    role: ANALYST
""")
    manager = ConfigManager(config_file=temp_config_file)
    connectors = manager.list_connectors()

    assert len(connectors) == 1
    assert isinstance(connectors[0], SnowflakeConnectorConfig)
    assert connectors[0].id == "my-snowflake"
    assert connectors[0].name == "my-snowflake"
    assert connectors[0].account == "test-account.us-east-1"
    assert connectors[0].user == "test@example.com"
    assert connectors[0].warehouse == "COMPUTE_WH"
    assert connectors[0].database == "TEST_DB"
    assert connectors[0].schema_name == "PUBLIC"
    assert connectors[0].role == "ANALYST"
    assert connectors[0].type == "snowflake"
    assert connectors[0].method == "externalbrowser"


def test_snowflake_config_without_method(temp_config_file: Path) -> None:
    """Configs without method field default to externalbrowser (backwards compat)."""
    temp_config_file.write_text("""
connectors:
  my-snowflake:
    account: test-account
    user: test@example.com
    warehouse: COMPUTE_WH
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-snowflake")

    assert connector is not None
    assert isinstance(connector, SnowflakeConnectorConfig)
    assert connector.method == "externalbrowser"


# --- Explicit type tests ---


def test_explicit_snowflake_type(temp_config_file: Path) -> None:
    """Test explicit type: snowflake config."""
    temp_config_file.write_text("""
connectors:
  my-sf:
    type: snowflake
    account: test-account
    user: test@example.com
    warehouse: COMPUTE_WH
    method: password
    password: secret123
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-sf")

    assert isinstance(connector, SnowflakeConnectorConfig)
    assert connector.method == "password"
    assert connector.password == "secret123"


def test_bigquery_config(temp_config_file: Path) -> None:
    """Test BigQuery config parsing."""
    temp_config_file.write_text("""
connectors:
  my-bq:
    type: bigquery
    project: my-gcp-project
    dataset: my_dataset
    location: US
    method: service-account
    keyfile: /path/to/keyfile.json
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-bq")

    assert isinstance(connector, BigQueryConnectorConfig)
    assert connector.project == "my-gcp-project"
    assert connector.dataset == "my_dataset"
    assert connector.location == "US"
    assert connector.method == "service-account"
    assert connector.keyfile == "/path/to/keyfile.json"


def test_bigquery_defaults(temp_config_file: Path) -> None:
    """Test BigQuery config defaults."""
    temp_config_file.write_text("""
connectors:
  my-bq:
    type: bigquery
    project: my-project
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-bq")

    assert isinstance(connector, BigQueryConnectorConfig)
    assert connector.method == "oauth"
    assert connector.job_execution_timeout_seconds == 300


def test_redshift_config(temp_config_file: Path) -> None:
    """Test Redshift config parsing."""
    temp_config_file.write_text("""
connectors:
  my-rs:
    type: redshift
    host: my-cluster.us-east-1.redshift.amazonaws.com
    user: admin
    database: mydb
    password: secret123
    schema: public
    port: 5439
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-rs")

    assert isinstance(connector, RedshiftConnectorConfig)
    assert connector.host == "my-cluster.us-east-1.redshift.amazonaws.com"
    assert connector.user == "admin"
    assert connector.database == "mydb"
    assert connector.password == "secret123"
    assert connector.schema_name == "public"
    assert connector.port == 5439
    assert connector.method == "database"


def test_redshift_iam_config(temp_config_file: Path) -> None:
    """Test Redshift IAM config parsing."""
    temp_config_file.write_text("""
connectors:
  my-rs:
    type: redshift
    host: my-cluster.us-east-1.redshift.amazonaws.com
    user: admin
    database: mydb
    method: iam
    iam_profile: my-profile
    cluster_id: my-cluster
    region: us-east-1
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-rs")

    assert isinstance(connector, RedshiftConnectorConfig)
    assert connector.method == "iam"
    assert connector.iam_profile == "my-profile"
    assert connector.cluster_id == "my-cluster"
    assert connector.region == "us-east-1"


# --- Type inference tests ---


def test_infer_bigquery_from_project_field(temp_config_file: Path) -> None:
    """Type inferred as bigquery when 'project' field present."""
    temp_config_file.write_text("""
connectors:
  my-bq:
    project: my-gcp-project
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-bq")

    assert isinstance(connector, BigQueryConnectorConfig)


def test_infer_redshift_from_host_field(temp_config_file: Path) -> None:
    """Type inferred as redshift when 'host' field present."""
    temp_config_file.write_text("""
connectors:
  my-rs:
    host: my-cluster.redshift.amazonaws.com
    user: admin
    database: mydb
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-rs")

    assert isinstance(connector, RedshiftConnectorConfig)


# --- Multi-connector tests ---


def test_multiple_connectors_mixed_types(temp_config_file: Path) -> None:
    """Test multiple connectors of different types."""
    temp_config_file.write_text("""
connectors:
  prod-snowflake:
    name: Production Snowflake
    account: prod-account
    user: prod@example.com
    warehouse: PROD_WH
  my-bq:
    type: bigquery
    project: my-project
  my-rs:
    type: redshift
    host: cluster.redshift.amazonaws.com
    user: admin
    database: mydb
    password: pass
""")
    manager = ConfigManager(config_file=temp_config_file)
    connectors = manager.list_connectors()

    assert len(connectors) == 3

    sf = manager.get_connector("prod-snowflake")
    assert isinstance(sf, SnowflakeConnectorConfig)
    assert sf.name == "Production Snowflake"

    bq = manager.get_connector("my-bq")
    assert isinstance(bq, BigQueryConnectorConfig)

    rs = manager.get_connector("my-rs")
    assert isinstance(rs, RedshiftConnectorConfig)


def test_get_connector_not_found(config_manager: ConfigManager) -> None:
    """Test getting a non-existent connector."""
    connector = config_manager.get_connector("non-existent-id")
    assert connector is None


# --- Snowflake auth field tests ---


def test_snowflake_keypair_fields(temp_config_file: Path) -> None:
    """Test Snowflake keypair config fields are parsed."""
    temp_config_file.write_text("""
connectors:
  my-sf:
    type: snowflake
    account: test-account
    user: test@example.com
    warehouse: COMPUTE_WH
    method: keypair
    private_key_path: /path/to/rsa_key.p8
    private_key_passphrase: mypassphrase
""")
    manager = ConfigManager(config_file=temp_config_file)
    connector = manager.get_connector("my-sf")

    assert isinstance(connector, SnowflakeConnectorConfig)
    assert connector.method == "keypair"
    assert connector.private_key_path == "/path/to/rsa_key.p8"
    assert connector.private_key_passphrase == "mypassphrase"
