"""Pydantic models for MC Bridge."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class BaseConnectorConfig(BaseModel):
    """Base configuration shared by all connector types."""

    id: str
    name: str


class SnowflakeConnectorConfig(BaseConnectorConfig):
    """Configuration for a Snowflake connector."""

    type: Literal["snowflake"] = "snowflake"
    account: str  # e.g., "xy12345.us-east-1"
    user: str  # e.g., "user@company.com"
    warehouse: str
    database: str | None = None
    schema_name: str | None = None
    role: str | None = None
    # Auth method: externalbrowser (default/SSO), password, keypair
    method: str = "externalbrowser"
    password: str | None = None
    # Key pair auth
    private_key: str | None = None  # inline PEM key
    private_key_path: str | None = None  # path to PEM key file
    private_key_passphrase: str | None = None


class BigQueryConnectorConfig(BaseConnectorConfig):
    """Configuration for a BigQuery connector."""

    type: Literal["bigquery"] = "bigquery"
    project: str
    dataset: str | None = None
    schema_name: str | None = None
    # Auth method: oauth (ADC), service-account (file path)
    method: str = "oauth"
    keyfile: str | None = None  # path to service account JSON
    location: str | None = None  # e.g. "US", "EU"
    job_execution_timeout_seconds: int = 300
    maximum_bytes_billed: int | None = None


class RedshiftConnectorConfig(BaseConnectorConfig):
    """Configuration for a Redshift connector."""

    type: Literal["redshift"] = "redshift"
    host: str
    port: int = 5439
    user: str
    database: str
    schema_name: str | None = None
    # Auth method: database (password), iam (uses AWS credential chain)
    method: str = "database"
    password: str | None = None
    iam_profile: str | None = None  # AWS profile name for iam method
    cluster_id: str | None = None
    region: str | None = None
    connect_timeout: int | None = None
    role: str | None = None
    sslmode: str | None = None


ConnectorConfig = Annotated[
    SnowflakeConnectorConfig | BigQueryConnectorConfig | RedshiftConnectorConfig,
    Field(discriminator="type"),
]


class QueryRequest(BaseModel):
    """Request model for executing a query."""

    connector_id: str
    sql: str
    database: str | None = None  # Override default database context
    schema_name: str | None = None  # Override default schema context
    timeout_seconds: int = 300
    limit: int = 100
    offset: int = 0


class QueryResult(BaseModel):
    """Result of a query execution."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float


class QueryResponse(BaseModel):
    """Response model for query execution."""

    success: bool
    result: QueryResult | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str
    connector_count: int


class TestConnectionResponse(BaseModel):
    """Response model for connection test."""

    success: bool
    message: str
    details: dict[str, Any] | None = None


class DatabasesResponse(BaseModel):
    """Response model for listing databases."""

    databases: list[str]


class SchemasResponse(BaseModel):
    """Response model for listing schemas."""

    schemas: list[str]


class TablesResponse(BaseModel):
    """Response model for listing tables."""

    tables: list[str]
