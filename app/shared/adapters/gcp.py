import json
import logging
import re
from datetime import datetime
from typing import Any, AsyncGenerator, cast
import structlog
from google.auth.credentials import Credentials as GoogleCredentials
from google.cloud import bigquery
from google.cloud import asset_v1
from google.oauth2 import service_account
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded
import tenacity

from app.shared.adapters.base import BaseAdapter
from app.models.gcp_connection import GCPConnection

logger = structlog.get_logger()

# BE-ADAPT-6/7: Retry decorator for GCP transient failures and expired credentials
gcp_retry = tenacity.retry(
    retry=tenacity.retry_if_exception_type((ServiceUnavailable, DeadlineExceeded)),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    stop=tenacity.stop_after_attempt(3),
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
)

# BE-ADAPT-8: Project ID format validation
PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]$")


def validate_project_id(project_id: str) -> bool:
    """Validate GCP project ID format."""
    return bool(PROJECT_ID_PATTERN.match(project_id))


class GCPAdapter(BaseAdapter):
    """
    Google Cloud Platform Adapter using BigQuery for costs and Cloud Asset Inventory for resources.

    Standard industry practice for GCP FinOps is to export billing data to BigQuery.
    """

    def __init__(self, connection: GCPConnection):
        self.connection = connection

        # BE-ADAPT-8: Fail-fast validation of project ID format
        if not validate_project_id(connection.project_id):
            error_msg = f"Invalid GCP project ID format: '{connection.project_id}'. Must be 6-30 lowercase letters, digits, or hyphens."
            logger.error("gcp_invalid_project_id", project_id=connection.project_id)
            raise ValueError(error_msg)

        self._credentials: GoogleCredentials | None = self._get_credentials()

    def _get_credentials(self) -> GoogleCredentials | None:
        """Initialize GCP credentials from service account JSON or environment."""
        if self.connection.service_account_json:
            try:
                info = json.loads(self.connection.service_account_json)
                return cast(
                    GoogleCredentials,
                    service_account.Credentials.from_service_account_info(info),  # type: ignore[no-untyped-call]
                )
            except Exception as e:
                logger.error("gcp_credentials_load_error", error=str(e))
        return None  # Fallback to default credentials

    def _get_bq_client(self) -> bigquery.Client:
        return bigquery.Client(
            project=self.connection.project_id, credentials=self._credentials
        )

    def _get_asset_client(self) -> asset_v1.AssetServiceClient:
        return asset_v1.AssetServiceClient(credentials=self._credentials)

    async def verify_connection(self) -> bool:
        """Verify GCP credentials by attempting to list projects or a lightweight check."""
        try:
            client = self._get_bq_client()
            # Just a simple check - list datasets in the billing project
            billing_project = (
                self.connection.billing_project_id or self.connection.project_id
            )
            list(client.list_datasets(project=billing_project, max_results=1))
            return True
        except Exception as e:
            logger.error("gcp_connection_verify_failed", error=str(e))
            return False

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
        include_credits: bool = True,  # Phase 5: CUD amortization
    ) -> list[dict[str, Any]]:
        """
        Fetch GCP costs from BigQuery billing export.
        Phase 5: Includes CUD credit extraction for amortized cost calculation.
        """
        if not self.connection.billing_dataset or not self.connection.billing_table:
            logger.warning(
                "gcp_bq_export_not_configured", project_id=self.connection.project_id
            )
            return []

        client = self._get_bq_client()

        # Determine and validate the table path (SEC-06)
        billing_project = (
            self.connection.billing_project_id or self.connection.project_id
        )
        billing_dataset = self.connection.billing_dataset
        billing_table = self.connection.billing_table

        # Strict validation: GCP resource IDs must be alphanumeric plus hyphens/underscores/dots
        safe_pattern = re.compile(r"^[a-zA-Z0-9.\-_]+$")
        if not all(
            safe_pattern.match(s)
            for s in [billing_project, billing_dataset, billing_table]
        ):
            error_msg = f"Invalid BigQuery table path: '{billing_project}.{billing_dataset}.{billing_table}'"
            logger.error(
                "gcp_bq_invalid_table_path",
                project=billing_project,
                dataset=billing_dataset,
                table=billing_table,
            )
            raise ValueError(error_msg)

        table_path = f"{billing_project}.{billing_dataset}.{billing_table}"

        query = self._build_cost_query(table_path)

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", start_date),
                bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", end_date),
            ]
        )

        try:
            query_job = client.query(query, job_config=job_config)
            results = query_job.result()

            return [self._parse_row(row) for row in results]
        except Exception as e:
            from app.shared.core.exceptions import AdapterError

            logger.error("gcp_bq_query_failed", table=table_path, error=str(e))
            raise AdapterError(f"GCP BigQuery cost fetch failed: {str(e)}") from e

    def _build_cost_query(self, table_path: str) -> str:
        """Constructs the BigQuery SQL for cost extraction."""
        return f"""
            SELECT
                service.description as service,
                SUM(cost) as cost_usd,
                SUM(
                    (SELECT SUM(c.amount) FROM UNNEST(credits) AS c)
                ) as total_credits,
                MAX(currency) as currency,
                TIMESTAMP_TRUNC(usage_start_time, DAY) as timestamp
            FROM `{table_path}`
            WHERE usage_start_time >= @start_date
              AND usage_start_time <= @end_date
            GROUP BY service, timestamp
            ORDER BY timestamp DESC
        """  # nosec: B608

    def _parse_row(self, row: Any) -> dict[str, Any]:
        """Normalizes a single GCP BigQuery result row."""
        return {
            "timestamp": row.timestamp,
            "service": row.service,
            "cost_usd": float(row.cost_usd),
            "credits": float(row.total_credits) if row.total_credits else 0.0,
            "amortized_cost": float(row.cost_usd) + float(row.total_credits or 0),
            "currency": row.currency,
            "region": "global",
            "source_adapter": "cur_billing_export",
        }

    async def get_amortized_costs(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> list[dict[str, Any]]:
        """
        Get GCP costs with CUD amortization applied.
        Phase 5: Cloud Parity - Returns amortized_cost which reflects CUD discounts.
        """
        records = await self.get_cost_and_usage(
            start_date, end_date, granularity, include_credits=True
        )
        # Return records with amortized_cost as the primary cost field
        return [
            {**r, "cost_usd": r.get("amortized_cost", r["cost_usd"])} for r in records
        ]

    async def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream GCP costs from BigQuery.
        Yields records one-by-one from the BigQuery result set.
        """
        records = await self.get_cost_and_usage(start_date, end_date, granularity)
        for record in records:
            yield record

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Discover GCP resources with OTel tracing.
        """
        from app.shared.core.tracing import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("gcp_discover_resources") as span:
            span.set_attribute("project_id", self.connection.project_id)
            span.set_attribute("resource_type", resource_type)

            client = self._get_asset_client()
            parent = f"projects/{self.connection.project_id}"

            # Map generic resource types to GCP content types
            asset_types = []
            if resource_type == "compute":
                asset_types = ["compute.googleapis.com/Instance"]
            elif resource_type == "storage":
                asset_types = ["storage.googleapis.com/Bucket"]

            try:
                response = client.list_assets(
                    request={
                        "parent": parent,
                        "asset_types": asset_types,
                        "content_type": asset_v1.ContentType.RESOURCE,
                    }
                )

                resources = []
                for asset in response:
                    res = asset.resource
                    resources.append(
                        {
                            "id": asset.name,
                            "name": asset.name.split("/")[-1],
                            "type": asset.asset_type,
                            "region": region or "global",
                            "provider": "gcp",
                            "metadata": {
                                "project_id": self.connection.project_id,
                                "data": str(res.data),
                            },
                        }
                    )
                return resources
            except Exception as e:
                logger.error("gcp_discovery_failed", error=str(e))
                return []
