"""Snowflake connector implementation."""

import time
from typing import Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection
from snowflake.connector.errors import DatabaseError, ProgrammingError

from mc_bridge.connectors.base import BaseConnector
from mc_bridge.models import ConnectorConfig, QueryResult


class SnowflakeConnector(BaseConnector):
    """Connector for Snowflake using browser-based SSO authentication."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._conn: SnowflakeConnection | None = None

    def connect(self) -> None:
        """Establish connection to Snowflake using browser-based SSO."""
        if self._connected and self._conn:
            return

        connect_params: dict[str, Any] = {
            "account": self.config.account,
            "user": self.config.user,
            "warehouse": self.config.warehouse,
            "authenticator": "externalbrowser",  # Opens browser for SSO
        }

        if self.config.database:
            connect_params["database"] = self.config.database
        if self.config.schema_name:
            connect_params["schema"] = self.config.schema_name
        if self.config.role:
            connect_params["role"] = self.config.role

        self._conn = snowflake.connector.connect(**connect_params)
        self._connected = True

    def disconnect(self) -> None:
        """Close the Snowflake connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    def execute_query(self, sql: str, timeout_seconds: int = 300) -> QueryResult:
        """Execute a SQL query and return results."""
        if not self._conn:
            raise RuntimeError("Not connected to Snowflake. Call connect() first.")

        start_time = time.perf_counter()

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, timeout=timeout_seconds)

            columns: list[str] = []
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]

            rows = cursor.fetchall()
            # Convert to list of lists for JSON serialization
            rows_list = [list(row) for row in rows]

            execution_time_ms = (time.perf_counter() - start_time) * 1000

            return QueryResult(
                columns=columns,
                rows=rows_list,
                row_count=len(rows_list),
                execution_time_ms=execution_time_ms,
            )
        finally:
            cursor.close()

    def test_connection(self) -> dict[str, Any]:
        """Test the connection and return status details."""
        try:
            self.connect()
            cursor = self._conn.cursor()  # type: ignore
            cursor.execute("SELECT CURRENT_VERSION(), CURRENT_USER(), CURRENT_WAREHOUSE()")
            row = cursor.fetchone()
            cursor.close()

            return {
                "success": True,
                "snowflake_version": row[0] if row else None,
                "current_user": row[1] if row else None,
                "current_warehouse": row[2] if row else None,
            }
        except (DatabaseError, ProgrammingError) as e:
            return {
                "success": False,
                "error": str(e),
            }

