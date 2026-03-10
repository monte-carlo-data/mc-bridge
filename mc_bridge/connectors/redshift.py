"""Redshift connector implementation."""

import time
from typing import Any

try:
    import redshift_connector
except ImportError:
    raise ImportError(
        "Install mc-bridge[redshift] to use Redshift connections: "
        "pip install 'mc-bridge[redshift]'"
    )

from mc_bridge.connectors.base import BaseConnector
from mc_bridge.models import QueryResult, RedshiftConnectorConfig


class RedshiftConnector(BaseConnector):
    """Connector for Redshift supporting password and IAM authentication."""

    def __init__(self, config: RedshiftConnectorConfig) -> None:
        super().__init__(config)
        self.config: RedshiftConnectorConfig = config
        self._conn: Any = None

    def connect(self) -> None:
        """Establish connection to Redshift."""
        if self._connected and self._conn:
            return

        params: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "database": self.config.database,
        }

        if self.config.method == "database":
            params["user"] = self.config.user
            params["password"] = self.config.password
        elif self.config.method == "iam":
            params["iam"] = True
            params["db_user"] = self.config.user
            if self.config.cluster_id:
                params["cluster_identifier"] = self.config.cluster_id
            if self.config.region:
                params["region"] = self.config.region
            if self.config.iam_profile:
                params["profile"] = self.config.iam_profile
        else:
            raise ValueError(f"Unsupported Redshift auth method: {self.config.method}")

        if self.config.sslmode:
            params["ssl"] = True
            params["sslmode"] = self.config.sslmode

        if self.config.connect_timeout:
            params["timeout"] = self.config.connect_timeout

        self._conn = redshift_connector.connect(**params)
        self._conn.autocommit = True
        self._connected = True

        if self.config.role:
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"SET ROLE {self.config.role}")
            finally:
                cursor.close()

    def disconnect(self) -> None:
        """Close the Redshift connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._connected = False

    def execute_query(self, sql: str, timeout_seconds: int = 300) -> QueryResult:
        """Execute a SQL query and return results."""
        if not self._conn:
            raise RuntimeError("Not connected to Redshift. Call connect() first.")

        start_time = time.perf_counter()

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql)

            columns: list[str] = []
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]

            rows = [list(row) for row in cursor.fetchall()]
            execution_time_ms = (time.perf_counter() - start_time) * 1000

            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                execution_time_ms=execution_time_ms,
            )
        finally:
            cursor.close()

    def test_connection(self) -> dict[str, Any]:
        """Test the connection and return status details."""
        try:
            self.connect()
            cursor = self._conn.cursor()
            cursor.execute("SELECT version(), current_user, current_database()")
            row = cursor.fetchone()
            cursor.close()

            return {
                "success": True,
                "redshift_version": row[0] if row else None,
                "current_user": row[1] if row else None,
                "current_database": row[2] if row else None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def list_databases(self) -> list[str]:
        """List all accessible databases."""
        return self._query_column(
            "SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname"
        )

    def list_schemas(self, database: str) -> list[str]:
        """List schemas in a database."""
        return self._query_column(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('information_schema', 'pg_catalog') "
            "ORDER BY schema_name"
        )

    def list_tables(self, database: str, schema: str) -> list[str]:
        """List tables in a schema."""
        return self._query_column(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' ORDER BY table_name"
        )

    def set_session_context(self, database: str | None, schema: str | None) -> None:
        """Set session schema context."""
        if not self._conn:
            raise RuntimeError("Not connected to Redshift. Call connect() first.")

        if schema:
            cursor = self._conn.cursor()
            try:
                cursor.execute(f"SET search_path TO {schema}")
            finally:
                cursor.close()

    def _query_column(self, sql: str) -> list[str]:
        """Execute a query and return the first column as a list."""
        if not self._conn:
            raise RuntimeError("Not connected to Redshift. Call connect() first.")

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql)
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
