"""Tests for configuration management."""

import tempfile
from pathlib import Path

import pytest

from mc_bridge.config import ConfigManager


@pytest.fixture
def temp_config_file() -> Path:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def config_manager(temp_config_file: Path) -> ConfigManager:
    """Create a ConfigManager with temporary storage."""
    return ConfigManager(config_file=temp_config_file)


def test_list_connectors_empty(config_manager: ConfigManager) -> None:
    """Test listing connectors when config file doesn't exist."""
    connectors = config_manager.list_connectors()
    assert connectors == []


def test_list_connectors_from_yaml(temp_config_file: Path) -> None:
    """Test listing connectors from YAML file."""
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
    assert connectors[0].id == "my-snowflake"
    assert connectors[0].name == "my-snowflake"
    assert connectors[0].account == "test-account.us-east-1"
    assert connectors[0].user == "test@example.com"
    assert connectors[0].warehouse == "COMPUTE_WH"
    assert connectors[0].database == "TEST_DB"
    assert connectors[0].schema_name == "PUBLIC"
    assert connectors[0].role == "ANALYST"


def test_get_connector(temp_config_file: Path) -> None:
    """Test getting a connector by ID."""
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
    assert connector.id == "my-snowflake"
    assert connector.account == "test-account"


def test_get_connector_not_found(config_manager: ConfigManager) -> None:
    """Test getting a non-existent connector."""
    connector = config_manager.get_connector("non-existent-id")
    assert connector is None


def test_multiple_connectors(temp_config_file: Path) -> None:
    """Test multiple connectors in config."""
    temp_config_file.write_text("""
connectors:
  prod-snowflake:
    name: Production Snowflake
    account: prod-account
    user: prod@example.com
    warehouse: PROD_WH
  dev-snowflake:
    account: dev-account
    user: dev@example.com
    warehouse: DEV_WH
""")
    manager = ConfigManager(config_file=temp_config_file)
    connectors = manager.list_connectors()

    assert len(connectors) == 2

    prod = manager.get_connector("prod-snowflake")
    assert prod is not None
    assert prod.name == "Production Snowflake"

    dev = manager.get_connector("dev-snowflake")
    assert dev is not None
    assert dev.name == "dev-snowflake"  # Falls back to ID when name not specified

