"""Base connector interface."""

from abc import ABC, abstractmethod
from typing import Any

from mc_bridge.models import BaseConnectorConfig, QueryResult


class BaseConnector(ABC):
    """Abstract base class for data connectors."""

    def __init__(self, config: BaseConnectorConfig) -> None:
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connector is connected."""
        return self._connected

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to the data source."""
        pass

    @abstractmethod
    def execute_query(self, sql: str, timeout_seconds: int = 300) -> QueryResult:
        """Execute a SQL query and return results."""
        pass

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Test the connection and return status details."""
        pass

    @abstractmethod
    def list_databases(self) -> list[str]:
        """List accessible databases/projects/datasets."""
        pass

    @abstractmethod
    def list_schemas(self, database: str) -> list[str]:
        """List schemas in a database."""
        pass

    @abstractmethod
    def list_tables(self, database: str, schema: str) -> list[str]:
        """List tables in a schema."""
        pass

    def set_session_context(self, database: str | None, schema: str | None) -> None:
        """Set session context. Override in subclasses that support it."""
        pass

    def __enter__(self) -> "BaseConnector":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()

