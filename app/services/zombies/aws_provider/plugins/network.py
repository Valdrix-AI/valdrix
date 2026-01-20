from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.zombies.registry import registry

logger = structlog.get_logger()

@registry.register("aws")
class OrphanLoadBalancersPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "orphan_load_balancers"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None, config: Any = None) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(session, "elbv2", region, credentials, config=config) as elb:
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
                                    healthy = [t for t in health.get("TargetHealthDescriptions", [])
                                              if t.get("TargetHealth", {}).get("State") == "healthy"]
                                    if healthy:
                                        has_healthy_targets = True
                                        break
                                if has_healthy_targets:
                                    break

                            if not has_healthy_targets:
                                from app.services.pricing.service import PricingService
                                monthly_cost = PricingService.estimate_monthly_waste(
                                    provider="aws",
                                    resource_type="elb",
                                    region=region
                                )
                                zombies.append({
                                    "resource_id": lb_arn,
                                    "resource_name": lb_name,
                                    "resource_type": "Load Balancer",
                                    "lb_type": lb_type,
                                    "monthly_cost": round(monthly_cost, 2),
                                    "recommendation": "Delete if no longer needed",
                                    "action": "delete_load_balancer",
                                    "supports_backup": False,
                                    "explainability_notes": f"{lb_type.upper()} has no healthy targets registered, meaning it is not serving any traffic.",
                                    "confidence_score": 0.95
                                })
                        except ClientError as e:
                            logger.warning("target_health_check_failed", lb=lb_name, error=str(e))

        except ClientError as e:
            logger.warning("orphan_lb_scan_error", error=str(e))

        return zombies

@registry.register("aws")
class UnderusedNatGatewaysPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "underused_nat_gateways"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None, config: Any = None) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(session, "ec2", region, credentials, config=config) as ec2:
                paginator = ec2.get_paginator("describe_nat_gateways")
                async with self._get_client(session, "cloudwatch", region, credentials, config=config) as cloudwatch:
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
                                    Dimensions=[{"Name": "NatGatewayId", "Value": nat_id}],
                                    StartTime=start_time, EndTime=end_time, Period=604800, Statistics=["Sum"]
                                )

                                total_connections = sum(d.get("Sum", 0) for d in metrics.get("Datapoints", []))

                                if total_connections < 100:
                                    from app.services.pricing.service import PricingService
                                    monthly_cost = PricingService.estimate_monthly_waste(
                                        provider="aws",
                                        resource_type="nat_gateway",
                                        region=region
                                    )
                                    zombies.append({
                                        "resource_id": nat_id,
                                        "resource_type": "NAT Gateway",
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "Delete or consolidate underused NAT Gateway",
                                        "action": "manual_review",
                                        "explainability_notes": f"NAT Gateway has extremely low traffic ({total_connections} connection attempts in 7 days).",
                                        "confidence_score": 0.85
                                    })
                            except ClientError as e:
                                logger.warning("nat_metric_fetch_failed", nat_id=nat_id, error=str(e))
        except ClientError as e:
             logger.warning("nat_scan_error", error=str(e))
        return zombies
