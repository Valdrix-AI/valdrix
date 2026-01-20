from datetime import datetime, timezone
from typing import List, Dict, Any
import structlog
from azure.identity.aio import ClientSecretCredential
from azure.mgmt.costmanagement.aio import CostManagementClient
from azure.mgmt.costmanagement.models import QueryDefinition, QueryTimePeriod, QueryDataset, QueryAggregation, QueryGrouping
from azure.mgmt.resource.resources.aio import ResourceManagementClient
from azure.core.exceptions import ServiceRequestError, ServiceResponseError
import tenacity

from app.services.adapters.base import BaseAdapter
from app.models.azure_connection import AzureConnection
from app.core.exceptions import AdapterError

logger = structlog.get_logger()

# BE-ADAPT-5: Retry decorator for Azure transient failures
azure_retry = tenacity.retry(
    retry=tenacity.retry_if_exception_type((ServiceRequestError, ServiceResponseError)),
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    stop=tenacity.stop_after_attempt(3),
    before_sleep=tenacity.before_sleep_log(logger, "warning")
)

class AzureAdapter(BaseAdapter):
    """
    Azure Cost Management Adapter using official Azure SDK.
    """
    
    def __init__(self, connection: AzureConnection):
        self.connection = connection
        self._credential = None
        self._cost_client = None
        self._resource_client = None

    async def _get_credentials(self):
        if not self._credential:
            self._credential = ClientSecretCredential(
                tenant_id=self.connection.azure_tenant_id,
                client_id=self.connection.client_id,
                client_secret=self.connection.client_secret
            )
        return self._credential

    async def _get_cost_client(self):
        if not self._cost_client:
            creds = await self._get_credentials()
            self._cost_client = CostManagementClient(credential=creds)
        return self._cost_client

    async def _get_resource_client(self):
        if not self._resource_client:
            creds = await self._get_credentials()
            self._resource_client = ResourceManagementClient(
                credential=creds,
                subscription_id=self.connection.subscription_id
            )
        return self._resource_client

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
            logger.error("azure_verify_failed", error=str(e), tenant_id=str(self.connection.azure_tenant_id))
            return False

    async def get_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY",
        cost_type: str = "ActualCost"  # Phase 5: Support ActualCost or AmortizedCost
    ) -> List[Dict[str, Any]]:
        """
        Fetch costs using Azure Query API.
        
        Args:
            cost_type: 'ActualCost' for on-demand costs, 'AmortizedCost' for RI/SP amortization.
        """
        try:
            client = await self._get_cost_client()
            
            # Azure Query API requires a scope (subscription in this case)
            scope = f"subscriptions/{self.connection.subscription_id}"
            
            query_definition = QueryDefinition(
                type=cost_type,  # Phase 5: Dynamic cost type
                timeframe="Custom",
                time_period=QueryTimePeriod(
                    from_property=start_date,
                    to=end_date
                ),
                dataset=QueryDataset(
                    granularity=granularity,
                    aggregation={
                        "totalCost": QueryAggregation(name="PreTaxCost", function="Sum")
                    },
                    grouping=[
                        QueryGrouping(type="Dimension", name="ServiceName"),
                        QueryGrouping(type="Dimension", name="ResourceLocation")
                    ]
                )
            )
            
            response = await client.query.usage(scope=scope, parameters=query_definition)
            
            records = []
            now = datetime.now(timezone.utc)
            if response and response.rows:
                # Column indices based on grouping: PreTaxCost (0), ServiceName (1), ResourceLocation (2), UsageDate (3)
                for row in response.rows:
                    dt = datetime.strptime(str(row[3]).strip(), "%Y%m%d").replace(tzinfo=timezone.utc)
                    # Phase 5: Mark as finalized if >3 days old
                    is_finalized = (now - dt).days > 3
                    records.append({
                        "timestamp": dt,
                        "service": row[1],
                        "region": row[2],
                        "cost_usd": float(row[0]),
                        "currency": "USD",
                        "amount_raw": float(row[0]),
                        "usage_type": "Usage",
                        "cost_type": cost_type,
                        "is_finalized": is_finalized
                    })
            return records
        except Exception as e:
            from app.core.exceptions import AdapterError
            logger.error("azure_cost_fetch_failed", error=str(e))
            raise AdapterError(f"Azure cost fetch failed: {str(e)}") from e

    async def get_amortized_costs(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> List[Dict[str, Any]]:
        """
        Fetch amortized costs (RI/Savings Plans spread across usage).
        Phase 5: Cloud Parity - Azure finalized cost support.
        """
        return await self.get_cost_and_usage(
            start_date, end_date, granularity, cost_type="AmortizedCost"
        )

    async def stream_cost_and_usage(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str = "DAILY"
    ) -> Any:
        """
        Stream Azure costs.
        Currently wraps the Query API (which is list-based) but yields individually to match interface.
        """
        records = await self.get_cost_and_usage(start_date, end_date, granularity)
        for r in records:
            yield r

    async def discover_resources(self, resource_type: str, region: str = None) -> List[Dict[str, Any]]:
        """
        Discover Azure resources with OTel tracing.
        """
        from app.core.tracing import get_tracer
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span("azure_discover_resources") as span:
            span.set_attribute("subscription_id", self.connection.subscription_id)
            
            try:
                client = await self._get_resource_client()
                resources = []
                async for resource in client.resources.list():
                    if resource_type and resource_type.lower() not in resource.type.lower():
                        continue
                    if region and region.lower() != resource.location.lower():
                        continue
                        
                    resources.append({
                        "id": resource.id,
                        "name": resource.name,
                        "type": resource.type,
                        "location": resource.location,
                        "tags": resource.tags
                    })
                return resources
            except Exception as e:
                logger.error("azure_resource_discovery_failed", error=str(e))
                return []
