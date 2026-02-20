from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.cognitiveservices import CognitiveServicesManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.search import SearchManagementClient

from app.modules.optimization.domain.cloud_api_budget import (
    allow_expensive_cloud_api_call,
)
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()


def _resource_group_from_id(resource_id: str) -> str | None:
    parts = resource_id.split("/")
    if len(parts) > 4 and parts[3].lower() == "resourcegroups":
        return parts[4]
    return None


def _as_positive_int(value: Any, *, default: int = 1) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _sum_total_metric(metrics_data: Any) -> float:
    total = 0.0
    values = getattr(metrics_data, "value", None)
    if not isinstance(values, list):
        return total
    for metric in values:
        series = getattr(metric, "timeseries", None)
        if not isinstance(series, list):
            continue
        for timeseries in series:
            data_points = getattr(timeseries, "data", None)
            if not isinstance(data_points, list):
                continue
            for data_point in data_points:
                value = getattr(data_point, "total", 0)
                if isinstance(value, (int, float)):
                    total += float(value)
    return total


@registry.register("azure")
class IdleAzureOpenAIPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_azure_openai"

    @staticmethod
    def _build_credential(credentials: dict[str, str] | None) -> Any:
        if credentials:
            return ClientSecretCredential(
                tenant_id=credentials.get("tenant_id", ""),
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
            )
        return DefaultAzureCredential()

    @staticmethod
    def _is_ptu_deployment(account: Any, deployment: Any) -> bool:
        candidates: list[str] = []
        for parent in (account, deployment):
            sku = getattr(parent, "sku", None)
            if sku is not None:
                name = str(getattr(sku, "name", "") or "").strip().lower()
                if name:
                    candidates.append(name)
            properties = getattr(parent, "properties", None)
            if properties is not None:
                sku_name = str(getattr(properties, "sku_name", "") or "").strip().lower()
                if sku_name:
                    candidates.append(sku_name)
        return any("provisioned" in value or "ptu" in value for value in candidates)

    @staticmethod
    def _ptu_units(account: Any, deployment: Any) -> int:
        for parent in (deployment, account):
            sku = getattr(parent, "sku", None)
            if sku is None:
                continue
            capacity = getattr(sku, "capacity", None)
            if capacity is not None:
                return _as_positive_int(capacity, default=1)
        return 1

    @staticmethod
    def _estimate_openai_monthly_cost(account: Any, deployment: Any) -> float:
        if not IdleAzureOpenAIPlugin._is_ptu_deployment(account, deployment):
            return 0.0

        units = IdleAzureOpenAIPlugin._ptu_units(account, deployment)
        region = str(getattr(account, "location", "") or "eastus").strip().lower()
        monthly_cost = PricingService.estimate_monthly_waste(
            provider="azure",
            resource_type="azure_openai_ptu",
            resource_size="ptu",
            region=region,
            quantity=float(units),
        )
        if monthly_cost <= 0:
            monthly_cost = 6000.0 * units
        return round(monthly_cost, 2)

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        del region, config, inventory, kwargs
        subscription_id = session
        zombies: list[dict[str, Any]] = []

        try:
            az_creds = self._build_credential(credentials)
            cognitive_client = CognitiveServicesManagementClient(az_creds, subscription_id)
            monitor_client = MonitorManagementClient(az_creds, subscription_id)

            for account in cognitive_client.accounts.list():
                if str(getattr(account, "kind", "")).strip().lower() != "openai":
                    continue

                resource_id = str(getattr(account, "id", "") or "").strip()
                account_name = str(getattr(account, "name", "") or "").strip()
                resource_group = _resource_group_from_id(resource_id)
                if not resource_id or not account_name or not resource_group:
                    continue

                deployments = cognitive_client.deployments.list(
                    resource_group_name=resource_group,
                    account_name=account_name,
                )
                for deployment in deployments:
                    dep_id = str(getattr(deployment, "id", "") or "").strip()
                    dep_name = str(getattr(deployment, "name", "") or "unknown").strip()
                    if not dep_id:
                        continue

                    properties = getattr(deployment, "properties", None)
                    model = getattr(properties, "model", None) if properties else None
                    model_name = str(getattr(model, "name", "") or "").strip()
                    if not model_name:
                        continue

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
                            aggregation="Total",
                        )

                        total_tokens = _sum_total_metric(metrics_data)
                        if total_tokens == 0:
                            monthly_cost = self._estimate_openai_monthly_cost(
                                account, deployment
                            )
                            zombies.append(
                                {
                                    "resource_id": dep_id,
                                    "resource_type": "Azure OpenAI Deployment",
                                    "resource_name": dep_name,
                                    "model": model_name,
                                    "monthly_cost": monthly_cost,
                                    "recommendation": "Delete unused deployment",
                                    "action": "delete_openai_deployment",
                                    "confidence_score": 1.0,
                                    "explainability_notes": (
                                        f"Deployment '{dep_name}' processed 0 tokens in "
                                        "the last 7 days."
                                    ),
                                }
                            )
                    except Exception as exc:
                        logger.warning(
                            "azure_openai_metric_failed",
                            dep=dep_name,
                            error=str(exc),
                        )
        except Exception as exc:
            logger.error("azure_openai_scan_error", error=str(exc))

        return zombies


@registry.register("azure")
class IdleAISearchPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_ai_search"

    @staticmethod
    def _build_credential(credentials: dict[str, str] | None) -> Any:
        if credentials:
            return ClientSecretCredential(
                tenant_id=credentials.get("tenant_id", ""),
                client_id=credentials.get("client_id", ""),
                client_secret=credentials.get("client_secret", ""),
            )
        return DefaultAzureCredential()

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        del region, config, inventory, kwargs
        subscription_id = session
        zombies: list[dict[str, Any]] = []

        try:
            az_creds = self._build_credential(credentials)
            search_client = SearchManagementClient(az_creds, subscription_id)
            monitor_client = MonitorManagementClient(az_creds, subscription_id)

            for service in search_client.services.list_by_subscription():
                sku_name = str(getattr(getattr(service, "sku", None), "name", "") or "")
                if sku_name.strip().lower() == "free":
                    continue

                resource_id = str(getattr(service, "id", "") or "").strip()
                if not resource_id:
                    continue

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
                            service=getattr(service, "name", "unknown"),
                        )
                        continue

                    metrics_data = monitor_client.metrics.list(
                        resource_uri=resource_id,
                        timespan=f"{start_time.isoformat()}/{end_time.isoformat()}",
                        interval="P1D",
                        metricnames="SearchQueries",
                        aggregation="Total",
                    )

                    total_queries = _sum_total_metric(metrics_data)
                    if total_queries == 0:
                        cost_map = {
                            "basic": 75.0,
                            "standard": 250.0,
                            "standard2": 1000.0,
                            "standard3": 2000.0,
                            "storage_optimized_l1": 3000.0,
                        }
                        normalized_sku = sku_name.strip().lower() or "unknown"
                        monthly_cost = cost_map.get(normalized_sku, 75.0)

                        zombies.append(
                            {
                                "resource_id": resource_id,
                                "resource_type": "Azure AI Search Service",
                                "resource_name": getattr(service, "name", "unknown"),
                                "sku": sku_name or "unknown",
                                "monthly_cost": monthly_cost,
                                "recommendation": "Delete unused search service",
                                "action": "delete_search_service",
                                "confidence_score": 0.95,
                                "explainability_notes": (
                                    "Search Service has received 0 queries in the last 7 days."
                                ),
                            }
                        )
                except Exception as exc:
                    logger.warning(
                        "azure_search_metric_failed",
                        service=getattr(service, "name", "unknown"),
                        error=str(exc),
                    )
        except Exception as exc:
            logger.error("azure_search_scan_error", error=str(exc))

        return zombies
