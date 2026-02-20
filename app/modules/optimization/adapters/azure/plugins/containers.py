"""
Azure Container Plugins - Zero-Cost Zombie Detection.

Detects idle AKS clusters and unused App Service Plans.
"""

from typing import List, Dict, Any
import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential

logger = structlog.get_logger()


@registry.register("azure")
class IdleAksClusterPlugin(ZombiePlugin):
    """Detect AKS clusters with no workloads."""

    @property
    def category_key(self) -> str:
        return "idle_azure_aks"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, str] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        """Scan for AKS clusters with control plane costs but no nodes."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        cost_records = kwargs.get("cost_records")

        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_idle_aks_clusters(days=7)

        # Fallback: Check for clusters with 0 nodes
        zombies = []
        try:
            from azure.mgmt.containerservice.aio import ContainerServiceClient

            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = ContainerServiceClient(az_creds, subscription_id)

            async for cluster in client.managed_clusters.list():
                total_nodes = sum(
                    pool.count or 0 for pool in (cluster.agent_pool_profiles or [])
                )

                if total_nodes == 0:
                    # AKS control plane: free for standard tier, ~$73/month for uptime SLA
                    estimated_cost = (
                        73.0 if cluster.sku and cluster.sku.tier == "Paid" else 0.0
                    )

                    zombies.append(
                        {
                            "resource_id": cluster.id,
                            "resource_name": cluster.name,
                            "resource_type": "AKS Cluster",
                            "location": cluster.location,
                            "node_count": 0,
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Delete empty cluster",
                            "action": "delete_aks",
                            "confidence_score": 0.90,
                            "explainability_notes": "AKS cluster has no agent pool nodes.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_aks_scan_error", error=str(e))

        return zombies


@registry.register("azure")
class UnusedAppServicePlansPlugin(ZombiePlugin):
    """Detect App Service Plans with no apps."""

    @property
    def category_key(self) -> str:
        return "unused_azure_app_service_plans"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, str] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        """Scan for App Service Plans with no apps deployed."""
        subscription_id = str(kwargs.get("subscription_id") or session or "")
        if not subscription_id:
            logger.warning(
                "azure_scan_missing_subscription_id", plugin=self.category_key
            )
            return []

        cost_records = kwargs.get("cost_records")

        if cost_records:
            from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer

            analyzer = AzureUsageAnalyzer(cost_records)
            return analyzer.find_unused_app_service_plans()

        zombies = []
        try:
            from azure.mgmt.web.aio import WebSiteManagementClient

            az_creds: ClientSecretCredential | DefaultAzureCredential
            if credentials:
                az_creds = ClientSecretCredential(
                    tenant_id=credentials.get("tenant_id", ""),
                    client_id=credentials.get("client_id", ""),
                    client_secret=credentials.get("client_secret", ""),
                )
            else:
                az_creds = DefaultAzureCredential()

            client = WebSiteManagementClient(az_creds, subscription_id)

            async for plan in client.app_service_plans.list():
                # Check if plan has any apps
                apps = []
                resource_id = str(plan.id or "")
                if not resource_id:
                    continue
                rg_name = resource_id.split("/")[4]
                async for app in client.web_apps.list_by_resource_group(
                    resource_group_name=rg_name
                ):
                    if app.server_farm_id and plan.id and plan.id in app.server_farm_id:
                        apps.append(app)

                if len(apps) == 0 and plan.sku and plan.sku.tier != "Free":
                    # Estimate cost based on tier
                    tier_costs = {
                        "Basic": 55,
                        "Standard": 73,
                        "Premium": 146,
                        "PremiumV2": 180,
                    }
                    estimated_cost = tier_costs.get(str(plan.sku.tier or ""), 50)

                    zombies.append(
                        {
                            "resource_id": plan.id,
                            "resource_name": plan.name,
                            "resource_type": "App Service Plan",
                            "location": plan.location,
                            "sku": f"{plan.sku.tier} ({plan.sku.name})"
                            if plan.sku
                            else "Unknown",
                            "monthly_cost": round(estimated_cost, 2),
                            "recommendation": "Delete if no apps will be deployed",
                            "action": "delete_app_service_plan",
                            "confidence_score": 0.95,
                            "explainability_notes": "App Service Plan has no web apps deployed.",
                        }
                    )
        except Exception as e:
            logger.warning("azure_app_service_plan_scan_error", error=str(e))

        return zombies
