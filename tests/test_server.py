"""Tests for the FastAPI server."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from mc_bridge.config import ConfigManager
from mc_bridge.server import app


@pytest.fixture
def temp_config_file() -> Path:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def mock_config_manager(temp_config_file: Path) -> ConfigManager:
    """Create a mock config manager with temporary storage."""
    return ConfigManager(config_file=temp_config_file)


@pytest.fixture
def client(mock_config_manager: ConfigManager) -> TestClient:
    """Create a test client with mocked config manager."""
    with patch("mc_bridge.server.config_manager", mock_config_manager):
        yield TestClient(app)


@pytest.fixture
def client_with_connector(temp_config_file: Path) -> TestClient:
    """Create a test client with a pre-configured connector."""
    temp_config_file.write_text("""
connectors:
  test-snowflake:
    account: test-account.us-east-1
    user: test@example.com
    warehouse: COMPUTE_WH
    database: TEST_DB
""")
    manager = ConfigManager(config_file=temp_config_file)
    with patch("mc_bridge.server.config_manager", manager):
        yield TestClient(app)


def test_health(client: TestClient) -> None:
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["connector_count"] == 0


def test_health_with_connector(client_with_connector: TestClient) -> None:
    """Test health check with configured connector."""
    response = client_with_connector.get("/health")
    assert response.status_code == 200
    assert response.json()["connector_count"] == 1


def test_list_connectors_empty(client: TestClient) -> None:
    """Test listing connectors when none exist."""
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    assert response.json() == []


def test_list_connectors(client_with_connector: TestClient) -> None:
    """Test listing connectors."""
    response = client_with_connector.get("/api/v1/connectors")
    assert response.status_code == 200

    connectors = response.json()
    assert len(connectors) == 1
    assert connectors[0]["id"] == "test-snowflake"
    assert connectors[0]["account"] == "test-account.us-east-1"


def test_get_connector(client_with_connector: TestClient) -> None:
    """Test getting a connector by ID."""
    response = client_with_connector.get("/api/v1/connectors/test-snowflake")
    assert response.status_code == 200
    assert response.json()["id"] == "test-snowflake"


def test_get_connector_not_found(client: TestClient) -> None:
    """Test getting a non-existent connector."""
    response = client.get("/api/v1/connectors/non-existent-id")
    assert response.status_code == 404


def test_execute_query_limit_exceeds_max(client_with_connector: TestClient) -> None:
    """Test that limit > 1000 returns 400 error."""
    response = client_with_connector.post(
        "/api/v1/query",
        json={
            "connector_id": "test-snowflake",
            "sql": "SELECT 1",
            "limit": 1001,
        },
    )
    assert response.status_code == 400
    assert "Limit cannot exceed 1000" in response.json()["detail"]


def test_execute_query_limit_at_max(client_with_connector: TestClient) -> None:
    """Test that limit = 1000 is accepted (doesn't return 400)."""
    response = client_with_connector.post(
        "/api/v1/query",
        json={
            "connector_id": "test-snowflake",
            "sql": "SELECT 1",
            "limit": 1000,
        },
    )
    # Will fail due to no actual connection, but not with 400
    assert response.status_code == 200

