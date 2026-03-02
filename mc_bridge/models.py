"""Pydantic models for MC Bridge."""

from typing import Any

from pydantic import BaseModel


class ConnectorConfig(BaseModel):
    """Configuration for a data connector."""

    id: str
    name: str
    account: str  # e.g., "xy12345.us-east-1"
    user: str  # e.g., "user@company.com"
    warehouse: str
    database: str | None = None
    schema_name: str | None = None
    role: str | None = None


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
