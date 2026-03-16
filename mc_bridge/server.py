"""FastAPI HTTP server for MC Bridge."""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from mc_bridge import __version__
from mc_bridge.certs import CERTS_DIR, is_ca_trusted
from mc_bridge.config import AnyConnectorConfig, config_manager
from mc_bridge.connectors.base import BaseConnector
from mc_bridge.models import (
    DashboardResponse,
    DatabasesResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SchemasResponse,
    TablesResponse,
    TestConnectionResponse,
)
from mc_bridge.security import CORS_EXTRA_ORIGINS, CORS_ORIGIN_REGEX

app = FastAPI(
    title="MC Bridge",
    description="Local bridge for Monte Carlo SaaS to connect to data sources",
    version=__version__,
)

# Add CORS middleware (must be added last to run first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_EXTRA_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _create_connector(config: AnyConnectorConfig) -> BaseConnector:
    """Create a connector instance based on config type. Lazy-imports drivers."""
    connector_type = config.type

    if connector_type == "snowflake":
        from mc_bridge.connectors.snowflake import SnowflakeConnector

        return SnowflakeConnector(config)
    elif connector_type == "bigquery":
        from mc_bridge.connectors.bigquery import BigQueryConnector

        return BigQueryConnector(config)
    elif connector_type == "redshift":
        from mc_bridge.connectors.redshift import RedshiftConnector

        return RedshiftConnector(config)
    else:
        raise ValueError(f"Unsupported connector type: {connector_type}")


# Store active connectors in memory
_active_connectors: dict[str, BaseConnector] = {}


def _get_or_create_connector(connector_id: str) -> BaseConnector:
    """Get an existing connector or create a new one."""
    if connector_id in _active_connectors:
        return _active_connectors[connector_id]

    config = config_manager.get_connector(connector_id)
    if not config:
        raise HTTPException(
            status_code=404, detail=f"Connector '{connector_id}' not found in config"
        )

    connector = _create_connector(config)
    _active_connectors[connector_id] = connector
    return connector


@app.get("/", response_model=DashboardResponse)
def dashboard() -> DashboardResponse:
    """Landing page showing bridge status."""
    connectors = config_manager.list_connectors()
    ca_cert_path = CERTS_DIR / "ca.pem"
    ca_trusted = is_ca_trusted(ca_cert_path)

    guidance = None
    if not ca_trusted:
        guidance = (
            "CA certificate is not trusted. Run: "
            "security add-trusted-cert -r trustRoot "
            f"-k ~/Library/Keychains/login.keychain-db {ca_cert_path}"
        )

    return DashboardResponse(
        message="MC Bridge is running",
        version=__version__,
        connector_count=len(connectors),
        https=True,
        ca_trusted=ca_trusted,
        ca_trust_guidance=guidance,
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""
    connectors = config_manager.list_connectors()
    return HealthResponse(
        status="ok",
        version=__version__,
        connector_count=len(connectors),
    )


@app.get("/api/v1/connectors")
def list_connectors() -> list[dict[str, Any]]:
    """List all configured connectors (from ~/.montecarlodata/mc-bridge.yaml)."""
    return [c.model_dump() for c in config_manager.list_connectors()]


@app.get("/api/v1/connectors/{connector_id}")
def get_connector(connector_id: str) -> dict[str, Any]:
    """Get a connector by ID."""
    connector = config_manager.get_connector(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")
    return connector.model_dump()


@app.post("/api/v1/connectors/{connector_id}/test", response_model=TestConnectionResponse)
def test_connection(connector_id: str) -> TestConnectionResponse:
    """Test a connector's connection."""
    connector = _get_or_create_connector(connector_id)
    result = connector.test_connection()

    return TestConnectionResponse(
        success=result.get("success", False),
        message="Connection successful" if result.get("success") else "Connection failed",
        details=result,
    )


@app.get("/api/v1/connectors/{connector_id}/databases", response_model=DatabasesResponse)
def list_databases(connector_id: str) -> DatabasesResponse:
    """List all accessible databases for a connector."""
    connector = _get_or_create_connector(connector_id)
    if not connector.is_connected:
        connector.connect()
    return DatabasesResponse(databases=connector.list_databases())


@app.get(
    "/api/v1/connectors/{connector_id}/databases/{database}/schemas",
    response_model=SchemasResponse,
)
def list_schemas(connector_id: str, database: str) -> SchemasResponse:
    """List schemas in a database."""
    connector = _get_or_create_connector(connector_id)
    if not connector.is_connected:
        connector.connect()
    return SchemasResponse(schemas=connector.list_schemas(database))


@app.get(
    "/api/v1/connectors/{connector_id}/databases/{database}/schemas/{schema}/tables",
    response_model=TablesResponse,
)
def list_tables(connector_id: str, database: str, schema: str) -> TablesResponse:
    """List tables in a schema."""
    connector = _get_or_create_connector(connector_id)
    if not connector.is_connected:
        connector.connect()
    return TablesResponse(tables=connector.list_tables(database, schema))


MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


@app.post("/api/v1/query", response_model=QueryResponse)
def execute_query(request: QueryRequest) -> QueryResponse:
    """Execute a SQL query on the specified connector."""
    if request.limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"Limit cannot exceed {MAX_LIMIT}",
        )

    try:
        connector = _get_or_create_connector(request.connector_id)

        if not connector.is_connected:
            connector.connect()

        # Set session context if database/schema provided
        if request.database or request.schema_name:
            connector.set_session_context(request.database, request.schema_name)

        wrapped_sql = f"SELECT * FROM ({request.sql}) LIMIT {request.limit} OFFSET {request.offset}"
        result = connector.execute_query(wrapped_sql, request.timeout_seconds)

        return QueryResponse(success=True, result=result)

    except Exception as e:
        return QueryResponse(success=False, error=str(e))
