"""Base connector interface."""

from abc import ABC, abstractmethod
from typing import Any

from mc_bridge.models import ConnectorConfig, QueryResult


class BaseConnector(ABC):
    """Abstract base class for data connectors."""

    def __init__(self, config: ConnectorConfig) -> None:
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

    def __enter__(self) -> "BaseConnector":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()

