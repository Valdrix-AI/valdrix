import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, AsyncGenerator, cast
import structlog
from google.auth.credentials import Credentials as GoogleCredentials
from google.cloud import bigquery
from google.cloud import asset_v1
from google.oauth2 import service_account
from google.api_core.exceptions import ServiceUnavailable, DeadlineExceeded
import tenacity

from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.resource_usage_projection import (
    project_cost_rows_to_resource_usage,
    resource_usage_lookback_window,
)
from app.shared.core.credentials import GCPCredentials
from app.shared.core.exceptions import ConfigurationError
from app.schemas.costs import CloudUsageSummary

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

    def __init__(self, credentials: GCPCredentials):
        self.credentials = credentials

        # BE-ADAPT-8: Fail-fast validation of project ID format
        if not validate_project_id(credentials.project_id):
            error_msg = f"Invalid GCP project ID format: '{credentials.project_id}'. Must be 6-30 lowercase letters, digits, or hyphens."
            logger.error("gcp_invalid_project_id", project_id=credentials.project_id)
            raise ConfigurationError(error_msg)

        self._credentials: GoogleCredentials | None = self._get_credentials()

    def _get_credentials(self) -> GoogleCredentials | None:
        """Initialize GCP credentials from service account JSON or environment."""
        if self.credentials.service_account_json:
            try:
                info = json.loads(
                    self.credentials.service_account_json.get_secret_value()
                )
                return cast(
                    GoogleCredentials,
                    service_account.Credentials.from_service_account_info(info),  # type: ignore[no-untyped-call]
                )
            except Exception as e:
                logger.error("gcp_credentials_load_error", error=str(e))
        return None  # Fallback to default credentials

    def _get_bq_client(self) -> bigquery.Client:
        return bigquery.Client(
            project=self.credentials.project_id, credentials=self._credentials
        )

    def _get_asset_client(self) -> asset_v1.AssetServiceClient:
        return asset_v1.AssetServiceClient(credentials=self._credentials)

    async def verify_connection(self) -> bool:
        """Verify GCP credentials by attempting to list projects or a lightweight check."""
        self._clear_last_error()
        try:
            client = self._get_bq_client()
            # Just a simple check - list datasets in the billing project
            billing_project = (
                self.credentials.billing_project_id or self.credentials.project_id
            )
            list(client.list_datasets(project=billing_project, max_results=1))
            return True
        except Exception as e:
            self._set_last_error_from_exception(
                e, prefix="GCP credential verification failed"
            )
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
        if not self.credentials.billing_dataset or not self.credentials.billing_table:
            logger.warning(
                "gcp_bq_export_not_configured", project_id=self.credentials.project_id
            )
            return []

        client = self._get_bq_client()

        # Determine and validate the table path (SEC-06)
        billing_project = (
            self.credentials.billing_project_id or self.credentials.project_id
        )
        billing_dataset = self.credentials.billing_dataset
        billing_table = self.credentials.billing_table

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
            raise ConfigurationError(error_msg)

        table_path = f"{billing_project}.{billing_dataset}.{billing_table}"

        query = self._build_cost_query(table_path, include_credits=include_credits)

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

    def _build_cost_query(self, table_path: str, include_credits: bool = True) -> str:
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
            "usage_type": "subscription",  # Standardize for GCP row
            "tags": {},  # Expanded tag support can be added to the BigQuery SQL if needed
            "amount_raw": float(row.cost_usd),
        }

    async def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        group_by_service: bool = True,
    ) -> CloudUsageSummary:
        """
        Fetch daily costs directly as a CloudUsageSummary from BigQuery.
        """
        from app.schemas.costs import CloudUsageSummary, CostRecord
        from decimal import Decimal

        start_dt = datetime.combine(
            start_date, datetime.min.time(), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        # Re-use the existing logic but map to CloudUsageSummary
        rows = await self.get_cost_and_usage(start_dt, end_dt, granularity="DAILY")

        records: list[CostRecord] = []
        total_cost = Decimal("0")
        by_service: dict[str, Decimal] = {}

        for row in rows:
            amount = Decimal(str(row["cost_usd"]))
            if amount <= 0:
                continue

            total_cost += amount
            service = row["service"]
            if group_by_service:
                by_service[service] = by_service.get(service, Decimal("0")) + amount

            records.append(
                CostRecord(
                    date=row["timestamp"],
                    amount=amount,
                    amount_raw=Decimal(str(row["amount_raw"])),
                    currency=row["currency"],
                    service=service,
                    region=row["region"],
                    usage_type=row["usage_type"],
                    tags=row.get("tags", {}),
                )
            )

        return CloudUsageSummary(
            tenant_id="anonymous",
            provider="gcp",
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            records=records,
            by_service=by_service if group_by_service else {},
        )

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

    def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream GCP costs from BigQuery.
        Yields records one-by-one from the BigQuery result set.
        """
        async def _iterate() -> AsyncGenerator[dict[str, Any], None]:
            records = await self.get_cost_and_usage(start_date, end_date, granularity)
            for row in records:
                yield row

        return _iterate()

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Discover GCP resources with OTel tracing.
        """
        self._clear_last_error()
        from app.shared.core.tracing import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("gcp_discover_resources") as span:
            span.set_attribute("project_id", self.credentials.project_id)
            span.set_attribute("resource_type", resource_type)

            client = self._get_asset_client()
            parent = f"projects/{self.credentials.project_id}"

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
                    metadata = {
                        "project_id": self.credentials.project_id,
                        "provider": "gcp",
                    }

                    # Extract machine type for compute instances
                    if asset.asset_type == "compute.googleapis.com/Instance":
                        data = res.data
                        # res.data is likely a dict or protobuf-like object
                        # We try to extract machineType if available
                        machine_type_full = str(data.get("machineType", ""))
                        if machine_type_full:
                            metadata["machine_type"] = machine_type_full.split("/")[-1]

                    resources.append(
                        {
                            "id": asset.name,
                            "name": asset.name.split("/")[-1],
                            "type": asset.asset_type,
                            "region": region or "global",
                            "provider": "gcp",
                            "metadata": metadata,
                        }
                    )
                return resources
            except Exception as e:
                self._set_last_error_from_exception(
                    e, prefix="GCP resource discovery failed"
                )
                logger.error("gcp_discovery_failed", error=str(e))
                return []

    async def get_resource_usage(
        self, service_name: str, resource_id: str | None = None
    ) -> list[dict[str, Any]]:
        self._clear_last_error()
        target_service = service_name.strip()
        if not target_service:
            return []

        start_date, end_date = resource_usage_lookback_window()
        try:
            cost_rows = await self.get_cost_and_usage(
                start_date=start_date,
                end_date=end_date,
                granularity="DAILY",
            )
        except Exception as exc:  # noqa: BLE001
            self._set_last_error_from_exception(
                exc, prefix="GCP resource usage lookup failed"
            )
            logger.warning(
                "gcp_resource_usage_failed",
                service_name=target_service,
                resource_id=resource_id,
                error=str(exc),
            )
            return []

        return project_cost_rows_to_resource_usage(
            cost_rows=cost_rows,
            service_name=target_service,
            resource_id=resource_id,
            default_provider="gcp",
            default_source_adapter="gcp_billing_export",
        )
