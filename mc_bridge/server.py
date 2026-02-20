"""FastAPI HTTP server for MC Bridge."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mc_bridge import __version__
from mc_bridge.config import config_manager
from mc_bridge.connectors.snowflake import SnowflakeConnector
from mc_bridge.models import (
    ConnectorConfig,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    TestConnectionResponse,
)
from mc_bridge.security import get_cors_origins

app = FastAPI(
    title="MC Bridge",
    description="Local bridge for Monte Carlo SaaS to connect to data sources",
    version=__version__,
)

# Add CORS middleware (must be added last to run first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Store active connectors in memory
_active_connectors: dict[str, SnowflakeConnector] = {}


def _get_or_create_connector(connector_id: str) -> SnowflakeConnector:
    """Get an existing connector or create a new one."""
    if connector_id in _active_connectors:
        return _active_connectors[connector_id]

    config = config_manager.get_connector(connector_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found in config")

    connector = SnowflakeConnector(config)
    _active_connectors[connector_id] = connector
    return connector


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""
    connectors = config_manager.list_connectors()
    return HealthResponse(
        status="ok",
        version=__version__,
        connector_count=len(connectors),
    )


@app.get("/api/v1/connectors", response_model=list[ConnectorConfig])
def list_connectors() -> list[ConnectorConfig]:
    """List all configured connectors (from ~/.montecarlodata/mc-bridge.yaml)."""
    return config_manager.list_connectors()


@app.get("/api/v1/connectors/{connector_id}", response_model=ConnectorConfig)
def get_connector(connector_id: str) -> ConnectorConfig:
    """Get a connector by ID."""
    connector = config_manager.get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")
    return connector


@app.post("/api/v1/connectors/{connector_id}/test", response_model=TestConnectionResponse)
def test_connection(connector_id: str) -> TestConnectionResponse:
    """Test a connector's connection (opens browser for SSO)."""
    connector = _get_or_create_connector(connector_id)
    result = connector.test_connection()

    return TestConnectionResponse(
        success=result.get("success", False),
        message="Connection successful" if result.get("success") else "Connection failed",
        details=result,
    )


@app.post("/api/v1/query", response_model=QueryResponse)
def execute_query(request: QueryRequest) -> QueryResponse:
    """Execute a SQL query on the specified connector."""
    try:
        connector = _get_or_create_connector(request.connector_id)

        if not connector.is_connected:
            connector.connect()

        result = connector.execute_query(request.sql, request.timeout_seconds)

        return QueryResponse(success=True, result=result)

    except Exception as e:
        return QueryResponse(success=False, error=str(e))

