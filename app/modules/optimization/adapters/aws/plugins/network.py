from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("aws")
class OrphanLoadBalancersPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "orphan_load_balancers"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(
                session, "elbv2", region, credentials, config=config
            ) as elb:
                paginator = elb.get_paginator("describe_load_balancers")
                async for page in paginator.paginate():
                    for lb in page.get("LoadBalancers", []):
                        lb_arn = lb["LoadBalancerArn"]
                        lb_name = lb["LoadBalancerName"]
                        lb_type = lb.get("Type", "application")

                        try:
                            tg_paginator = elb.get_paginator("describe_target_groups")
                            tg_iterator = tg_paginator.paginate(LoadBalancerArn=lb_arn)

                            has_healthy_targets = False
                            async for tg_page in tg_iterator:
                                for tg in tg_page.get("TargetGroups", []):
                                    health = await elb.describe_target_health(
                                        TargetGroupArn=tg["TargetGroupArn"]
                                    )
                                    healthy = [
                                        t
                                        for t in health.get(
                                            "TargetHealthDescriptions", []
                                        )
                                        if t.get("TargetHealth", {}).get("State")
                                        == "healthy"
                                    ]
                                    if healthy:
                                        has_healthy_targets = True
                                        break
                                if has_healthy_targets:
                                    break

                            if not has_healthy_targets:
                                from app.modules.reporting.domain.pricing.service import (
                                    PricingService,
                                )

                                monthly_cost = PricingService.estimate_monthly_waste(
                                    provider="aws", resource_type="elb", region=region
                                )
                                zombies.append(
                                    {
                                        "resource_id": lb_arn,
                                        "resource_name": lb_name,
                                        "resource_type": "Load Balancer",
                                        "lb_type": lb_type,
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "Delete if no longer needed",
                                        "action": "delete_load_balancer",
                                        "supports_backup": False,
                                        "explainability_notes": f"{lb_type.upper()} has no healthy targets registered, meaning it is not serving any traffic.",
                                        "confidence_score": 0.95,
                                    }
                                )
                        except ClientError as e:
                            logger.warning(
                                "target_health_check_failed", lb=lb_name, error=str(e)
                            )

        except ClientError as e:
            logger.warning("orphan_lb_scan_error", error=str(e))

        return zombies


@registry.register("aws")
class UnderusedNatGatewaysPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "underused_nat_gateways"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        days = 7

        # CUR-First Detection (Zero API Cost)
        cur_records = kwargs.get("cur_records")
        if cur_records:
            from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer

            analyzer = CURUsageAnalyzer(cur_records)
            return analyzer.find_idle_nat_gateways(days=days)

        try:
            async with self._get_client(
                session, "ec2", region, credentials, config=config
            ) as ec2:
                paginator = ec2.get_paginator("describe_nat_gateways")
                async with self._get_client(
                    session, "cloudwatch", region, credentials, config=config
                ) as cloudwatch:
                    async for page in paginator.paginate():
                        for nat in page.get("NatGateways", []):
                            if nat["State"] != "available":
                                continue

                            nat_id = nat["NatGatewayId"]
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=7)

                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/NATGateway",
                                    MetricName="ConnectionAttemptCount",
                                    Dimensions=[
                                        {"Name": "NatGatewayId", "Value": nat_id}
                                    ],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=604800,
                                    Statistics=["Sum"],
                                )

                                total_connections = sum(
                                    d.get("Sum", 0)
                                    for d in metrics.get("Datapoints", [])
                                )

                                if total_connections < 100:
                                    from app.modules.reporting.domain.pricing.service import (
                                        PricingService,
                                    )

                                    monthly_cost = (
                                        PricingService.estimate_monthly_waste(
                                            provider="aws",
                                            resource_type="nat_gateway",
                                            region=region,
                                        )
                                    )
                                    zombies.append(
                                        {
                                            "resource_id": nat_id,
                                            "resource_type": "NAT Gateway",
                                            "monthly_cost": round(monthly_cost, 2),
                                            "recommendation": "Delete or consolidate underused NAT Gateway",
                                            "action": "manual_review",
                                            "explainability_notes": f"NAT Gateway has extremely low traffic ({total_connections} connection attempts in 7 days).",
                                            "confidence_score": 0.85,
                                        }
                                    )
                            except ClientError as e:
                                logger.warning(
                                    "nat_metric_fetch_failed",
                                    nat_id=nat_id,
                                    error=str(e),
                                )
        except ClientError as e:
            logger.warning("nat_scan_error", error=str(e))
        return zombies


@registry.register("aws")
class IdleCloudFrontPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_cloudfront_distributions"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        # CloudFront is global, but typically accessed via us-east-1
        if region != "us-east-1":
            return []

        zombies = []
        days = 7

        try:
            async with self._get_client(
                session, "cloudfront", "us-east-1", credentials, config=config
            ) as cf:
                paginator = cf.get_paginator("list_distributions")

                async with self._get_client(
                    session, "cloudwatch", "us-east-1", credentials, config=config
                ) as cw:
                    async for page in paginator.paginate():
                        for dist in page.get("DistributionList", {}).get("Items", []):
                            if not dist["Enabled"]:
                                continue

                            dist_id = dist["Id"]
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days)

                                # Metric: Requests
                                metrics = await cw.get_metric_statistics(
                                    Namespace="AWS/CloudFront",
                                    MetricName="Requests",
                                    Dimensions=[
                                        {"Name": "DistributionId", "Value": dist_id},
                                        {"Name": "Region", "Value": "Global"},
                                    ],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=86400 * days,
                                    Statistics=["Sum"],
                                )

                                total_requests = sum(
                                    d["Sum"] for d in metrics.get("Datapoints", [])
                                )

                                if (
                                    total_requests < 100
                                ):  # Arbitrary "low usage" threshold
                                    zombies.append(
                                        {
                                            "resource_id": dist_id,
                                            "resource_type": "CloudFront Distribution",
                                            "resource_name": dist.get(
                                                "DomainName", dist_id
                                            ),
                                            "monthly_cost": 0.0,  # Hard to estimate base cost (mostly transfer), but existing is a risk
                                            "recommendation": "Disable and delete if unused",
                                            "action": "disable_cloudfront_distribution",
                                            "confidence_score": 0.9,
                                            "explainability_notes": f"Distribution has had only {int(total_requests)} requests in the last {days} days.",
                                        }
                                    )
                            except ClientError as e:
                                logger.warning(
                                    "cloudfront_metric_failed",
                                    dist=dist_id,
                                    error=str(e),
                                )

        except ClientError as e:
            logger.warning("cloudfront_scan_error", error=str(e))

        return zombies
