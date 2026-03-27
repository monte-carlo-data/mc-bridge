"""Tests for the FastAPI server."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from mc_bridge import __version__
from mc_bridge.auth import EXPECTED_AUDIENCE, EXPECTED_ISSUER
from mc_bridge.config import ConfigManager
from mc_bridge.server import app


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Generate an RSA keypair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key_pem


@pytest.fixture
def test_keys_dir(tmp_path: Path, rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> Path:
    """Create a temp keys directory with the test public key."""
    keys = tmp_path / "keys"
    keys.mkdir()
    keys.joinpath("current.pem").write_bytes(rsa_keypair[1])
    return keys


@pytest.fixture
def auth_header(rsa_keypair: tuple[rsa.RSAPrivateKey, bytes]) -> dict[str, str]:
    """Create a valid Authorization header."""
    private_key, _ = rsa_keypair
    token = pyjwt.encode(
        {
            "sub": "test-user",
            "aud": EXPECTED_AUDIENCE,
            "iss": EXPECTED_ISSUER,
            "exp": int(time.time()) + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    return {"Authorization": f"Bearer {token}"}


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
def client(mock_config_manager: ConfigManager, test_keys_dir: Path) -> TestClient:
    """Create a test client with mocked config manager and test keys."""
    with (
        patch("mc_bridge.server.config_manager", mock_config_manager),
        patch("mc_bridge.auth.KEYS_DIR", test_keys_dir),
    ):
        yield TestClient(app)


@pytest.fixture
def client_with_snowflake(temp_config_file: Path, test_keys_dir: Path) -> TestClient:
    """Create a test client with a pre-configured Snowflake connector."""
    temp_config_file.write_text("""
connectors:
  test-snowflake:
    account: test-account.us-east-1
    user: test@example.com
    warehouse: COMPUTE_WH
    database: TEST_DB
""")
    manager = ConfigManager(config_file=temp_config_file)
    with (
        patch("mc_bridge.server.config_manager", manager),
        patch("mc_bridge.auth.KEYS_DIR", test_keys_dir),
    ):
        yield TestClient(app)


@pytest.fixture
def client_with_mixed(temp_config_file: Path, test_keys_dir: Path) -> TestClient:
    """Create a test client with connectors of all types."""
    temp_config_file.write_text("""
connectors:
  test-snowflake:
    account: test-account.us-east-1
    user: test@example.com
    warehouse: COMPUTE_WH
  test-bigquery:
    type: bigquery
    project: my-project
  test-redshift:
    type: redshift
    host: cluster.redshift.amazonaws.com
    user: admin
    database: mydb
    password: pass
""")
    manager = ConfigManager(config_file=temp_config_file)
    with (
        patch("mc_bridge.server.config_manager", manager),
        patch("mc_bridge.auth.KEYS_DIR", test_keys_dir),
    ):
        yield TestClient(app)


# --- Exempt endpoints (no auth required) ---


def test_dashboard(client: TestClient) -> None:
    """Test dashboard landing page endpoint (no auth required)."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert data["message"] == "MC Bridge is running"
    assert "version" in data
    assert data["connector_count"] == 0
    assert data["https"] is True
    assert "ca_trusted" in data


def test_dashboard_with_connectors(client_with_mixed: TestClient) -> None:
    """Test dashboard shows correct connector count."""
    response = client_with_mixed.get("/")
    assert response.status_code == 200
    assert response.json()["connector_count"] == 3


def test_health(client: TestClient) -> None:
    """Test health check endpoint returns status-only."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "version" not in data
    assert "connector_count" not in data


# --- Auth enforcement on API endpoints ---


def test_api_requires_auth(client: TestClient) -> None:
    """API endpoints return 401 without auth header."""
    response = client.get("/api/v1/connectors")
    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized"


def test_api_rejects_invalid_token(client: TestClient) -> None:
    """API endpoints return 401 with invalid token."""
    response = client.get("/api/v1/connectors", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_api_rejects_missing_bearer_prefix(client: TestClient) -> None:
    """API endpoints return 401 without Bearer prefix."""
    response = client.get("/api/v1/connectors", headers={"Authorization": "Token abc"})
    assert response.status_code == 401


# --- Authed API endpoints ---


def test_list_connectors_empty(client: TestClient, auth_header: dict[str, str]) -> None:
    """Test listing connectors when none exist."""
    response = client.get("/api/v1/connectors", headers=auth_header)
    assert response.status_code == 200
    assert response.json() == []


def test_list_connectors(client_with_snowflake: TestClient, auth_header: dict[str, str]) -> None:
    """Test listing connectors."""
    response = client_with_snowflake.get("/api/v1/connectors", headers=auth_header)
    assert response.status_code == 200

    connectors = response.json()
    assert len(connectors) == 1
    assert connectors[0]["id"] == "test-snowflake"
    assert connectors[0]["account"] == "test-account.us-east-1"
    assert connectors[0]["type"] == "snowflake"


def test_list_connectors_mixed(client_with_mixed: TestClient, auth_header: dict[str, str]) -> None:
    """Test listing connectors returns all types."""
    response = client_with_mixed.get("/api/v1/connectors", headers=auth_header)
    assert response.status_code == 200

    connectors = response.json()
    assert len(connectors) == 3
    types = {c["type"] for c in connectors}
    assert types == {"snowflake", "bigquery", "redshift"}


def test_get_connector(client_with_snowflake: TestClient, auth_header: dict[str, str]) -> None:
    """Test getting a connector by ID."""
    response = client_with_snowflake.get("/api/v1/connectors/test-snowflake", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["id"] == "test-snowflake"


def test_get_connector_not_found(client: TestClient, auth_header: dict[str, str]) -> None:
    """Test getting a non-existent connector."""
    response = client.get("/api/v1/connectors/non-existent-id", headers=auth_header)
    assert response.status_code == 404


def test_execute_query_limit_exceeds_max(
    client_with_snowflake: TestClient, auth_header: dict[str, str]
) -> None:
    """Test that limit > 1000 returns 400 error."""
    response = client_with_snowflake.post(
        "/api/v1/query",
        json={
            "connector_id": "test-snowflake",
            "sql": "SELECT 1",
            "limit": 1001,
        },
        headers=auth_header,
    )
    assert response.status_code == 400
    assert "Limit cannot exceed 1000" in response.json()["detail"]


def test_execute_query_limit_at_max(
    client_with_snowflake: TestClient, auth_header: dict[str, str]
) -> None:
    """Test that limit = 1000 is accepted (doesn't return 400)."""
    response = client_with_snowflake.post(
        "/api/v1/query",
        json={
            "connector_id": "test-snowflake",
            "sql": "SELECT 1",
            "limit": 1000,
        },
        headers=auth_header,
    )
    # Will fail due to no actual connection, but not with 400
    assert response.status_code == 200


def test_execute_query_prepends_version_comment(
    client_with_snowflake: TestClient, auth_header: dict[str, str]
) -> None:
    """Test that queries are tagged with the mc-bridge version comment."""
    mock_connector = MagicMock()
    mock_connector.is_connected = True
    mock_connector.execute_query.return_value = {"columns": [], "rows": []}

    with patch("mc_bridge.server._get_or_create_connector", return_value=mock_connector):
        client_with_snowflake.post(
            "/api/v1/query",
            json={"connector_id": "test-snowflake", "sql": "SELECT 1"},
            headers=auth_header,
        )

    actual_sql = mock_connector.execute_query.call_args[0][0]
    expected_comment = f"-- query executed by mc-bridge {__version__}"
    assert actual_sql.startswith(expected_comment)
