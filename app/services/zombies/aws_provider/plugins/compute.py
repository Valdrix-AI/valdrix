from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.zombies.registry import registry
from app.services.adapters.rate_limiter import RateLimiter
from app.services.pricing.service import PricingService

logger = structlog.get_logger()
cloudwatch_limiter = RateLimiter(rate_per_second=1.0) # Conservative limit for CloudWatch

@registry.register("aws")
class UnusedElasticIpsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "unused_elastic_ips"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None, config: Any = None) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(session, "ec2", region, credentials, config=config) as ec2:
                response = await ec2.describe_addresses()

                for addr in response.get("Addresses", []):
                    # SEC: Check AssociationId and NetworkInterfaceId properly
                    # Legitimate EIP usage: instance-attached or NI-attached (including NAT Gateways)
                    is_zombie = not addr.get("InstanceId") and not addr.get("NetworkInterfaceId") and not addr.get("AssociationId")
                    
                    if is_zombie:
                        zombies.append({
                            "resource_id": addr.get("AllocationId", addr.get("PublicIp")),
                            "resource_type": "Elastic IP",
                            "public_ip": addr.get("PublicIp"),
                            "monthly_cost": PricingService.estimate_monthly_waste(
                                provider="aws",
                                resource_type="ip",
                                region=region
                            ),
                            "backup_cost_monthly": 0,
                            "recommendation": "Release if not needed",
                            "action": "release_elastic_ip",
                            "supports_backup": False,
                            "explainability_notes": "Static IP address is not associated with any running instance, network interface, or association ID.",
                            "confidence_score": 0.99
                        })
        except ClientError as e:
            logger.warning("eip_scan_error", error=str(e))

        return zombies

@registry.register("aws")
class IdleInstancesPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_instances"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None, config: Any = None) -> List[Dict[str, Any]]:
        zombies = []
        instances = []
        cpu_threshold = 2.0  # Tightened from 5% (BE-ZD-3)
        days = 14            # Extended from 7 days (BE-ZD-3)

        try:
            async with await self._get_client(session, "ec2", region, credentials, config=config) as ec2:
                paginator = ec2.get_paginator("describe_instances")
                async for page in paginator.paginate(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                ):
                    for reservation in page.get("Reservations", []):
                        for instance in reservation.get("Instances", []):
                            # BE-ZD-3: Skip instances with "batch", "scheduled", or "cron" in tags
                            tags = {t['Key'].lower(): t['Value'].lower() for t in instance.get("Tags", [])}
                            if any(k in ["workload", "type"] and any(v in tags[k] for v in ["batch", "scheduled", "cron"]) for k in tags):
                                continue
                            if any("batch" in k or "batch" in tags[k] for k in tags):
                                continue

                            instances.append({
                                "id": instance["InstanceId"],
                                "type": instance.get("InstanceType", "unknown"),
                                "launch_time": instance.get("LaunchTime"),
                                "tags": tags
                            })

            if not instances:
                return []

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            async with self._get_client(session, "cloudwatch", region, credentials, config=config) as cloudwatch:
                # Batch metrics in 500-instance chunks (AWS limit)
                for i in range(0, len(instances), 500):
                    # BE-ZD-2: Rate limiting for CloudWatch queries
                    await cloudwatch_limiter.acquire()
                    
                    batch = instances[i:i + 500]
                    queries = []
                    for idx, inst in enumerate(batch):
                        queries.append({
                            "Id": f"m{idx}",
                            "MetricStat": {
                                "Metric": {
                                    "Namespace": "AWS/EC2",
                                    "MetricName": "CPUUtilization",
                                    "Dimensions": [{"Name": "InstanceId", "Value": inst["id"]}]
                                },
                                "Period": 86400 * days,
                                "Stat": "Average"
                            }
                        })

                    results = await cloudwatch.get_metric_data(
                        MetricDataQueries=queries,
                        StartTime=start_time,
                        EndTime=end_time
                    )

                    # Map results back to instances
                    for idx, inst in enumerate(batch):
                        res = next((r for r in results.get("MetricDataResults", []) if r["Id"] == f"m{idx}"), None)
                        if res and res.get("Values"):
                            avg_cpu = res["Values"][0]
                            
                            # BE-ZD-3: Heuristic improvement
                            if avg_cpu < cpu_threshold:
                                monthly_cost = PricingService.estimate_monthly_waste(
                                    provider="aws",
                                    resource_type="instance",
                                    resource_size=inst['type'],
                                    region=region
                                )

                                zombies.append({
                                    "resource_id": inst["id"],
                                    "resource_type": "EC2 Instance",
                                    "instance_type": inst["type"],
                                    "avg_cpu_percent": round(avg_cpu, 2),
                                    "monthly_cost": round(monthly_cost, 2),
                                    "launch_time": inst["launch_time"].isoformat() if inst["launch_time"] else "",
                                    "recommendation": "Stop or terminate if not needed",
                                    "action": "stop_instance",
                                    "supports_backup": True,
                                    "explainability_notes": f"Instance has shown extremely low CPU utilization (avg {round(avg_cpu, 2)}%) over a 14-day analysis period. High confidence zombie resource.",
                                    "confidence_score": 0.98  # Raised from 0.92
                                })

        except ClientError as e:
            logger.warning("idle_instance_scan_error", error=str(e))

        return zombies
