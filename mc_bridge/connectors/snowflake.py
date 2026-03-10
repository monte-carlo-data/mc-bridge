"""Snowflake connector implementation."""

import time
from typing import Any

try:
    import snowflake.connector
    from snowflake.connector import SnowflakeConnection
    from snowflake.connector.errors import DatabaseError, ProgrammingError
except ImportError:
    raise ImportError(
        "Install mc-bridge[snowflake] to use Snowflake connections: "
        "pip install 'mc-bridge[snowflake]'"
    )

from mc_bridge.connectors.base import BaseConnector
from mc_bridge.models import QueryResult, SnowflakeConnectorConfig


class SnowflakeConnector(BaseConnector):
    """Connector for Snowflake supporting multiple authentication methods."""

    def __init__(self, config: SnowflakeConnectorConfig) -> None:
        super().__init__(config)
        self.config: SnowflakeConnectorConfig = config
        self._conn: SnowflakeConnection | None = None

    def connect(self) -> None:
        """Establish connection to Snowflake."""
        if self._connected and self._conn:
            return

        connect_params: dict[str, Any] = {
            "account": self.config.account,
            "user": self.config.user,
            "warehouse": self.config.warehouse,
        }

        if self.config.database:
            connect_params["database"] = self.config.database
        if self.config.schema_name:
            connect_params["schema"] = self.config.schema_name
        if self.config.role:
            connect_params["role"] = self.config.role

        method = self.config.method

        if method == "externalbrowser":
            connect_params["authenticator"] = "externalbrowser"

        elif method == "password":
            if not self.config.password:
                raise ValueError("password required for method='password'")
            connect_params["password"] = self.config.password

        elif method == "keypair":
            connect_params["private_key"] = self._load_private_key()

        else:
            raise ValueError(f"Unsupported Snowflake auth method: {method}")

        self._conn = snowflake.connector.connect(**connect_params)
        self._connected = True

    def _load_private_key(self) -> bytes:
        """Load and serialize private key to DER format for snowflake connector."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        passphrase = (
            self.config.private_key_passphrase.encode()
            if self.config.private_key_passphrase
            else None
        )

        if self.config.private_key_path:
            with open(self.config.private_key_path, "rb") as f:
                pem_data = f.read()
            key = load_pem_private_key(pem_data, password=passphrase)
        elif self.config.private_key:
            key = load_pem_private_key(
                self.config.private_key.encode(), password=passphrase
            )
        else:
            raise ValueError(
                "private_key or private_key_path required for method='keypair'"
            )

        return key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

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

    def list_databases(self) -> list[str]:
        """List all accessible databases."""
        if not self._conn:
            raise RuntimeError("Not connected to Snowflake. Call connect() first.")

        cursor = self._conn.cursor()
        try:
            cursor.execute("SHOW DATABASES")
            # Column 1 (index 1) is "name" in SHOW DATABASES output
            return [row[1] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def list_schemas(self, database: str) -> list[str]:
        """List schemas in a database."""
        if not self._conn:
            raise RuntimeError("Not connected to Snowflake. Call connect() first.")

        cursor = self._conn.cursor()
        try:
            cursor.execute(f"SHOW SCHEMAS IN DATABASE {database}")
            # Column 1 (index 1) is "name" in SHOW SCHEMAS output
            return [row[1] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def list_tables(self, database: str, schema: str) -> list[str]:
        """List tables in a schema."""
        if not self._conn:
            raise RuntimeError("Not connected to Snowflake. Call connect() first.")

        cursor = self._conn.cursor()
        try:
            cursor.execute(f"SHOW TABLES IN {database}.{schema}")
            # Column 1 (index 1) is "name" in SHOW TABLES output
            return [row[1] for row in cursor.fetchall()]
        finally:
            cursor.close()

    def set_session_context(self, database: str | None, schema: str | None) -> None:
        """Set session database/schema context for subsequent queries."""
        if not self._conn:
            raise RuntimeError("Not connected to Snowflake. Call connect() first.")

        cursor = self._conn.cursor()
        try:
            if database:
                cursor.execute(f"USE DATABASE {database}")
            if schema:
                cursor.execute(f"USE SCHEMA {schema}")
        finally:
            cursor.close()
