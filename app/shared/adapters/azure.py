import logging
from datetime import date, datetime, timezone
from typing import Any, AsyncGenerator
import structlog
from azure.identity.aio import ClientSecretCredential
from azure.mgmt.costmanagement.aio import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition,
    QueryTimePeriod,
    QueryDataset,
    QueryAggregation,
    QueryGrouping,
)
from azure.mgmt.resource.resources.aio import ResourceManagementClient
from azure.mgmt.compute.aio import ComputeManagementClient
from azure.core.exceptions import ServiceRequestError, ServiceResponseError
import tenacity

from app.shared.adapters.base import BaseAdapter
from app.shared.core.credentials import AzureCredentials
from app.shared.core.exceptions import ConfigurationError
from app.schemas.costs import CloudUsageSummary

logger = structlog.get_logger()

# BE-ADAPT-5: Retry decorator for Azure transient failures
azure_retry = tenacity.retry(
    retry=tenacity.retry_if_exception_type((ServiceRequestError, ServiceResponseError)),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    stop=tenacity.stop_after_attempt(3),
    before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
)


class AzureAdapter(BaseAdapter):
    """
    Azure Cost Management Adapter using official Azure SDK.
    """

    def __init__(self, credentials: AzureCredentials):
        self.credentials = credentials
        self._credential: ClientSecretCredential | None = None
        self._cost_client: CostManagementClient | None = None
        self._resource_client: ResourceManagementClient | None = None
        self._compute_client: ComputeManagementClient | None = None

    async def _get_credentials(self) -> ClientSecretCredential:
        if not self._credential:
            if not self.credentials.client_secret:
                raise ConfigurationError(
                    "Azure client_secret is required for client secret auth"
                )
            self._credential = ClientSecretCredential(
                tenant_id=self.credentials.tenant_id,
                client_id=self.credentials.client_id,
                client_secret=self.credentials.client_secret.get_secret_value(),
            )
        return self._credential

    async def _get_cost_client(self) -> CostManagementClient:
        if not self._cost_client:
            creds = await self._get_credentials()
            self._cost_client = CostManagementClient(credential=creds)
        return self._cost_client

    async def _get_resource_client(self) -> ResourceManagementClient:
        if not self._resource_client:
            creds = await self._get_credentials()
            self._resource_client = ResourceManagementClient(
                credential=creds, subscription_id=self.credentials.subscription_id
            )
        return self._resource_client

    async def _get_compute_client(self) -> ComputeManagementClient:
        if not self._compute_client:
            creds = await self._get_credentials()
            self._compute_client = ComputeManagementClient(
                credential=creds, subscription_id=self.credentials.subscription_id
            )
        return self._compute_client

    async def verify_connection(self) -> bool:
        """
        Verify Azure Service Principal credentials by attempting to list resource groups.
        """
        try:
            client = await self._get_resource_client()
            async for _ in client.resource_groups.list():
                break
            return True
        except Exception as e:
            logger.error(
                "azure_verify_failed",
                error=str(e),
                tenant_id=str(self.credentials.tenant_id),
            )
            return False

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
        cost_type: str = "ActualCost",
    ) -> list[dict[str, Any]]:
        """Fetch costs using Azure Query API."""
        try:
            client = await self._get_cost_client()
            scope = f"subscriptions/{self.credentials.subscription_id}"

            query_definition = self._build_query_definition(
                start_date, end_date, granularity, cost_type
            )

            response = await client.query.usage(
                scope=scope, parameters=query_definition
            )

            if response and response.rows:
                return [self._parse_row(row, cost_type) for row in response.rows]
            return []
        except Exception as e:
            from app.shared.core.exceptions import AdapterError

            logger.error("azure_cost_fetch_failed", error=str(e))
            raise AdapterError(f"Azure cost fetch failed: {str(e)}") from e

    def _build_query_definition(
        self, start: datetime, end: datetime, granularity: str, cost_type: str
    ) -> QueryDefinition:
        """Constructs the Azure Query API definition."""
        return QueryDefinition(
            type=cost_type,
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity=granularity,
                aggregation={
                    "totalCost": QueryAggregation(name="PreTaxCost", function="Sum")
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ServiceName"),
                    QueryGrouping(type="Dimension", name="ResourceLocation"),
                    QueryGrouping(type="Dimension", name="ChargeType"),
                    QueryGrouping(type="Dimension", name="UsageDate"),
                ],
            ),
        )

    def _parse_row(self, row: list[Any], cost_type: str) -> dict[str, Any]:
        """Normalizes a single Azure result row."""
        # Indices: PreTaxCost (0), ServiceName (1), ResourceLocation (2), ChargeType (3), UsageDate (4)
        raw_date = str(row[4]).strip()

        # Try multiple formats (Azure can be inconsistent depending on the API version/export)
        dt = None
        for fmt in ["%Y%m%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"]:
            try:
                dt = datetime.strptime(raw_date, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

        if not dt:
            # Fallback for ISO date if simple strptime fails
            try:
                normalized = raw_date.replace("Z", "+00:00")
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            except ValueError:
                logger.error("azure_date_parse_failed", raw_val=raw_date)
                # Fallback to now but log error
                dt = datetime.now(timezone.utc)

        now = datetime.now(timezone.utc)

        return {
            "timestamp": dt,
            "service": row[1],
            "region": row[2],
            "cost_usd": float(row[0]),
            "currency": "USD",
            "amount_raw": float(row[0]),
            "usage_type": row[3],
            "cost_type": cost_type,
            "is_finalized": (now - dt).days > 3,
            "source_adapter": "explorer_api",
            "tags": {},  # Azure Query API dimensions can be expanded for tags if needed
        }

    async def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        group_by_service: bool = True,
    ) -> CloudUsageSummary:
        """
        Fetch daily costs and return a standardized CloudUsageSummary.
        Optimized for scheduler integration.
        """
        from app.schemas.costs import CloudUsageSummary, CostRecord
        from decimal import Decimal

        start_dt = datetime.combine(
            start_date, datetime.min.time(), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

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
            provider="azure",
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
        Fetch amortized costs (RI/Savings Plans spread across usage).
        Phase 5: Cloud Parity - Azure finalized cost support.
        """
        return await self.get_cost_and_usage(
            start_date, end_date, granularity, cost_type="AmortizedCost"
        )

    def stream_cost_and_usage(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[dict[str, Any], None]:
        return self._stream_cost_and_usage_impl(start_date, end_date, granularity)

    async def _stream_cost_and_usage_impl(
        self, start_date: datetime, end_date: datetime, granularity: str = "DAILY"
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream Azure costs.
        Currently wraps the Query API (which is list-based) but yields individually to match interface.
        """
        records = await self.get_cost_and_usage(start_date, end_date, granularity)
        for record in records:
            yield record

    async def discover_resources(
        self, resource_type: str, region: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Discover Azure resources with OTel tracing.
        """
        from app.shared.core.tracing import get_tracer

        tracer = get_tracer(__name__)

        with tracer.start_as_current_span("azure_discover_resources") as span:
            span.set_attribute("subscription_id", self.credentials.subscription_id)

            try:
                resources = []
                # Specialized discovery for compute resources to get VM Size (used for ARM analysis)
                if resource_type.lower() == "compute":
                    comp_client = await self._get_compute_client()
                    async for vm in comp_client.virtual_machines.list_all():
                        if region and region.lower() != vm.location.lower():
                            continue
                        resources.append(
                            {
                                "id": vm.id,
                                "name": vm.name,
                                "type": "Microsoft.Compute/virtualMachines",
                                "location": vm.location,
                                "tags": vm.tags or {},
                                "metadata": {
                                    "size": vm.hardware_profile.vm_size
                                    if vm.hardware_profile
                                    else "unknown",
                                    "provider": "azure",
                                },
                            }
                        )
                    return resources

                client = await self._get_resource_client()
                async for resource in client.resources.list():
                    if (
                        resource_type
                        and resource_type.lower() not in resource.type.lower()
                    ):
                        continue
                    if region and region.lower() != resource.location.lower():
                        continue

                    resources.append(
                        {
                            "id": resource.id,
                            "name": resource.name,
                            "type": resource.type,
                            "location": resource.location,
                            "tags": resource.tags or {},
                        }
                    )
                return resources
            except Exception as e:
                logger.error("azure_resource_discovery_failed", error=str(e))
                return []
