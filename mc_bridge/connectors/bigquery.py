"""BigQuery connector implementation."""

import time
from typing import Any

try:
    from google.cloud import bigquery
except ImportError:
    raise ImportError(
        "Install mc-bridge[bigquery] to use BigQuery connections: "
        "pip install 'mc-bridge[bigquery]'"
    )

from mc_bridge.connectors.base import BaseConnector
from mc_bridge.models import BigQueryConnectorConfig, QueryResult


class BigQueryConnector(BaseConnector):
    """Connector for BigQuery supporting OAuth (ADC) and service account auth."""

    def __init__(self, config: BigQueryConnectorConfig) -> None:
        super().__init__(config)
        self.config: BigQueryConnectorConfig = config
        self._client: bigquery.Client | None = None
        self._default_dataset: bigquery.DatasetReference | None = None

    def connect(self) -> None:
        """Establish connection to BigQuery."""
        if self._connected and self._client:
            return

        credentials = self._get_credentials()
        self._client = bigquery.Client(
            project=self.config.project,
            credentials=credentials,
            location=self.config.location,
        )

        # Set default dataset if configured
        if self.config.dataset:
            self._default_dataset = self._client.dataset(
                self.config.dataset, project=self.config.project
            )

        self._connected = True

    def _get_credentials(self) -> Any:
        """Build credentials based on configured auth method."""
        method = self.config.method

        if method == "oauth":
            import google.auth

            credentials, _ = google.auth.default()
            return credentials

        elif method == "service-account":
            from google.oauth2 import service_account

            if not self.config.keyfile:
                raise ValueError("keyfile required for method='service-account'")
            return service_account.Credentials.from_service_account_file(
                self.config.keyfile
            )

        else:
            raise ValueError(f"Unsupported BigQuery auth method: {method}")

    def disconnect(self) -> None:
        """Close the BigQuery client."""
        if self._client:
            self._client.close()
            self._client = None
        self._default_dataset = None
        self._connected = False

    def execute_query(self, sql: str, timeout_seconds: int = 300) -> QueryResult:
        """Execute a SQL query and return results."""
        if not self._client:
            raise RuntimeError("Not connected to BigQuery. Call connect() first.")

        start_time = time.perf_counter()

        job_config = bigquery.QueryJobConfig()
        if self.config.maximum_bytes_billed is not None:
            job_config.maximum_bytes_billed = self.config.maximum_bytes_billed
        if self._default_dataset:
            job_config.default_dataset = self._default_dataset

        query_job = self._client.query(sql, job_config=job_config, timeout=timeout_seconds)
        result = query_job.result(timeout=timeout_seconds)

        columns = [field.name for field in result.schema]
        rows = [list(row.values()) for row in result]
        execution_time_ms = (time.perf_counter() - start_time) * 1000

        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            execution_time_ms=execution_time_ms,
        )

    def test_connection(self) -> dict[str, Any]:
        """Test the connection and return status details."""
        try:
            self.connect()
            query_job = self._client.query("SELECT 1 AS test")  # type: ignore
            list(query_job.result())

            return {
                "success": True,
                "project": self.config.project,
                "location": self.config.location,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def list_databases(self) -> list[str]:
        """List datasets in the project (BQ datasets map to the database level)."""
        if not self._client:
            raise RuntimeError("Not connected to BigQuery. Call connect() first.")

        return [
            ds.dataset_id for ds in self._client.list_datasets(self.config.project)
        ]

    def list_schemas(self, database: str) -> list[str]:
        """List schemas — BQ has a flat dataset model, so return the dataset itself."""
        return [database]

    def list_tables(self, database: str, schema: str) -> list[str]:
        """List tables in a dataset."""
        if not self._client:
            raise RuntimeError("Not connected to BigQuery. Call connect() first.")

        dataset_ref = self._client.dataset(database, project=self.config.project)
        return [t.table_id for t in self._client.list_tables(dataset_ref)]

    def set_session_context(self, database: str | None, schema: str | None) -> None:
        """Set default dataset for subsequent queries."""
        if not self._client:
            raise RuntimeError("Not connected to BigQuery. Call connect() first.")

        if database:
            self._default_dataset = self._client.dataset(
                database, project=self.config.project
            )
