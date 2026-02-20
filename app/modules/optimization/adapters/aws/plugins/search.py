from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import structlog

from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()


@registry.register("aws")
class IdleOpenSearchPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_opensearch_domains"

    @staticmethod
    def _as_positive_int(value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _client_id_from_domain(status: dict[str, Any]) -> str | None:
        domain_id = str(status.get("DomainId") or "")
        if not domain_id:
            return None
        parts = domain_id.split("/", 1)
        return parts[0] if parts and parts[0] else None

    @staticmethod
    async def _metric_has_non_zero(
        *,
        cloudwatch: Any,
        dimensions: list[dict[str, str]],
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        statistic: str,
    ) -> bool:
        metric = await cloudwatch.get_metric_statistics(
            Namespace="AWS/ES",
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=[statistic],
        )
        datapoints = metric.get("Datapoints")
        if not isinstance(datapoints, list):
            return False
        for point in datapoints:
            if not isinstance(point, dict):
                continue
            value = point.get(statistic)
            if isinstance(value, (int, float)) and value > 0:
                return True
        return False

    @staticmethod
    def _estimate_monthly_cost(status: dict[str, Any], region: str) -> float:
        cluster_config = status.get("ClusterConfig") or {}
        if not isinstance(cluster_config, dict):
            cluster_config = {}

        instance_type = str(cluster_config.get("InstanceType") or "default").lower()
        instance_count = IdleOpenSearchPlugin._as_positive_int(
            cluster_config.get("InstanceCount"),
            default=1,
        )

        monthly_cost = PricingService.estimate_monthly_waste(
            provider="aws",
            resource_type="opensearch",
            resource_size=instance_type,
            region=region,
            quantity=float(instance_count),
        )

        dedicated_master_enabled = bool(cluster_config.get("DedicatedMasterEnabled"))
        if dedicated_master_enabled:
            master_type = str(
                cluster_config.get("DedicatedMasterType") or "default"
            ).lower()
            master_count = IdleOpenSearchPlugin._as_positive_int(
                cluster_config.get("DedicatedMasterCount"),
                default=3,
            )
            monthly_cost += PricingService.estimate_monthly_waste(
                provider="aws",
                resource_type="opensearch_master",
                resource_size=master_type,
                region=region,
                quantity=float(master_count),
            )

        return round(monthly_cost, 2)

    async def scan(
        self,
        session: Any,
        region: str,
        credentials: Dict[str, Any] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        del inventory, kwargs
        zombies: list[dict[str, Any]] = []

        try:
            async with self._get_client(
                session, "opensearch", region, credentials, config=config
            ) as client, self._get_client(
                session, "cloudwatch", region, credentials, config=config
            ) as cloudwatch:
                response = await client.list_domain_names()
                domain_names = response.get("DomainNames")
                if not isinstance(domain_names, list):
                    return zombies

                end_time = datetime.now(timezone.utc)
                start_time = end_time - timedelta(days=7)

                for domain_entry in domain_names:
                    if not isinstance(domain_entry, dict):
                        continue
                    domain_name = str(domain_entry.get("DomainName") or "").strip()
                    if not domain_name:
                        continue

                    desc = await client.describe_domain(DomainName=domain_name)
                    status = desc.get("DomainStatus")
                    if not isinstance(status, dict):
                        continue
                    if status.get("Deleted"):
                        continue

                    arn = str(status.get("ARN") or "").strip()
                    if not arn:
                        continue

                    dimensions = [{"Name": "DomainName", "Value": domain_name}]
                    client_id = self._client_id_from_domain(status)
                    if client_id:
                        dimensions.append({"Name": "ClientId", "Value": client_id})

                    has_data = await self._metric_has_non_zero(
                        cloudwatch=cloudwatch,
                        dimensions=dimensions,
                        metric_name="SearchableDocuments",
                        start_time=start_time,
                        end_time=end_time,
                        statistic="Average",
                    )

                    # Metrics vary by engine/version; evaluate both canonical names.
                    has_requests = await self._metric_has_non_zero(
                        cloudwatch=cloudwatch,
                        dimensions=dimensions,
                        metric_name="SearchRate",
                        start_time=start_time,
                        end_time=end_time,
                        statistic="Average",
                    ) or await self._metric_has_non_zero(
                        cloudwatch=cloudwatch,
                        dimensions=dimensions,
                        metric_name="SearchRequestRate",
                        start_time=start_time,
                        end_time=end_time,
                        statistic="Sum",
                    )

                    if has_data and not has_requests:
                        zombies.append(
                            {
                                "resource_id": arn,
                                "resource_type": "AWS OpenSearch Domain",
                                "resource_name": domain_name,
                                "region": region,
                                "monthly_cost": self._estimate_monthly_cost(
                                    status, region
                                ),
                                "recommendation": "Snapshot and delete unused OpenSearch domain",
                                "action": "snapshot_and_delete_opensearch",
                                "confidence_score": 0.9,
                                "explainability_notes": (
                                    f"Domain '{domain_name}' has indexed data but no search "
                                    "activity in the last 7 days."
                                ),
                            }
                        )
        except Exception as exc:
            logger.error("aws_opensearch_scan_error", error=str(exc))

        return zombies
