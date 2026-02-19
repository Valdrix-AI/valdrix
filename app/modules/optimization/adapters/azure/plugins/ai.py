from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.search import SearchManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.cloud_api_budget import (
    allow_expensive_cloud_api_call,
)
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("azure")
class IdleAzureOpenAIPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_azure_openai"

    async def scan(
        self,
        session: str,  # acts as subscription_id for Azure
        credentials: Any,
        region: str = "global",
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        subscription_id = session
        zombies = []

        try:
            # 1. List Cognitive Accounts (OpenAI kind)
            cognitive_client = CognitiveServicesManagementClient(credentials, subscription_id)
            monitor_client = MonitorManagementClient(credentials, subscription_id)

            accounts = cognitive_client.accounts.list()
            for account in accounts:
                if account.kind != "OpenAI":
                    continue

                # 2. List Deployments
                deployments = cognitive_client.deployments.list(
                    resource_group_name=account.id.split("/")[4],
                    account_name=account.name
                )

                for deployment in deployments:
                    dep_id = deployment.id
                    dep_name = deployment.name
                    model_name = deployment.properties.model.name

                    # 3. Check Metric: Processed Inference Tokens (7 days)
                    end_time = datetime.now(timezone.utc)
                    start_time = end_time - timedelta(days=7)
                    
                    try:
                        allowed = await allow_expensive_cloud_api_call(
                            "azure_monitor",
                            operation="metrics.list",
                        )
                        if not allowed:
                            logger.warning(
                                "azure_monitor_budget_exhausted",
                                plugin=self.category_key,
                                deployment=dep_name,
                            )
                            continue

                        metrics_data = monitor_client.metrics.list(
                            resource_uri=dep_id,
                            timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                            interval="P1D",
                            metricnames="ProcessedInferenceTokens",
                            aggregation="Total"
                        )

                        total_tokens = 0
                        if metrics_data.value:
                            for timeseries in metrics_data.value[0].timeseries:
                                for data in timeseries.data:
                                    total_tokens += (data.total or 0)

                        if total_tokens == 0:
                            # Cost Estimation (Rough)
                            is_ptu = False # TODO: check SKU
                            monthly_cost = 0.0
                            if is_ptu:
                                monthly_cost = 6000.0 # Example
                            
                            zombies.append({
                                "resource_id": dep_id,
                                "resource_type": "Azure OpenAI Deployment",
                                "resource_name": dep_name,
                                "model": model_name,
                                "monthly_cost": monthly_cost,
                                "recommendation": "Delete unused deployment",
                                "action": "delete_openai_deployment",
                                "confidence_score": 1.0, 
                                "explainability_notes": f"Deployment '{dep_name}' processed 0 tokens in the last 7 days."
                            })

                    except Exception as e:
                        logger.warning("azure_openai_metric_failed", dep=dep_name, error=str(e))

        except Exception as e:
            logger.error("azure_openai_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class IdleAISearchPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_ai_search"

    async def scan(
        self,
        session: str,
        credentials: Any,
        region: str = "global",
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        subscription_id = session
        zombies = []

        try:
            search_client = SearchManagementClient(credentials, subscription_id)
            monitor_client = MonitorManagementClient(credentials, subscription_id)

            services = search_client.services.list_by_subscription()

            for service in services:
                # 0. Check SKU - Free tier implies no cost waste (but clutter)
                if service.sku.name.lower() == "free":
                    continue

                # 1. Check Metric: SearchQueriesPerSecond (if 0 sum over 7 days = unused)
                resource_id = service.id
                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(days=7)

                try:
                    allowed = await allow_expensive_cloud_api_call(
                        "azure_monitor",
                        operation="metrics.list",
                    )
                    if not allowed:
                        logger.warning(
                            "azure_monitor_budget_exhausted",
                            plugin=self.category_key,
                            service=service.name,
                        )
                        continue

                    metrics_data = monitor_client.metrics.list(
                        resource_uri=resource_id,
                        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                        interval="P1D",
                        metricnames="SearchQueries",
                        aggregation="Total"
                    )
                    
                    total_queries = 0
                    if metrics_data.value:
                        for timeseries in metrics_data.value[0].timeseries:
                            for data in timeseries.data:
                                total_queries += (data.total or 0)
                    
                    if total_queries == 0:
                        # Estimate Cost based on SKU
                        cost_map = {
                            "basic": 75.0,
                            "standard": 250.0,
                            "standard2": 1000.0,
                            "standard3": 2000.0,
                            "storage_optimized_l1": 3000.0
                        }
                        monthly_cost = cost_map.get(service.sku.name.lower(), 75.0)

                        zombies.append({
                            "resource_id": resource_id,
                            "resource_type": "Azure AI Search Service",
                            "resource_name": service.name,
                            "sku": service.sku.name,
                            "monthly_cost": monthly_cost,
                            "recommendation": "Delete unused search service",
                            "action": "delete_search_service",
                            "confidence_score": 0.95,
                            "explainability_notes": "Search Service has received 0 queries in the last 7 days."
                        })

                except Exception as e:
                    logger.warning("azure_search_metric_failed", service=service.name, error=str(e))

        except Exception as e:
             logger.error("azure_search_scan_error", error=str(e))

        return zombies
