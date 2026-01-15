from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.pricing.service import PricingService

logger = structlog.get_logger()

class UnusedElasticIpsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "unused_elastic_ips"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with await self._get_client(session, "ec2", region, credentials) as ec2:
                response = await ec2.describe_addresses()

                for addr in response.get("Addresses", []):
                    if not addr.get("InstanceId") and not addr.get("NetworkInterfaceId"):
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
                            "explainability_notes": "Static IP address is not associated with any running instance or network interface.",
                            "confidence_score": 0.98
                        })
        except ClientError as e:
            logger.warning("eip_scan_error", error=str(e))

        return zombies

class IdleInstancesPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_instances"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None) -> List[Dict[str, Any]]:
        zombies = []
        instances = []
        cpu_threshold = 5.0
        days = 7

        try:
            async with await self._get_client(session, "ec2", region, credentials) as ec2:
                paginator = ec2.get_paginator("describe_instances")
                async for page in paginator.paginate(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                ):
                    for reservation in page.get("Reservations", []):
                        for instance in reservation.get("Instances", []):
                            instances.append({
                                "id": instance["InstanceId"],
                                "type": instance.get("InstanceType", "unknown"),
                                "launch_time": instance.get("LaunchTime")
                            })

            if not instances:
                return []

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            async with await self._get_client(session, "cloudwatch", region, credentials) as cloudwatch:
                # Batch metrics in 500-instance chunks (AWS limit)
                for i in range(0, len(instances), 500):
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
                                    "explainability_notes": f"Instance has shown very low CPU utilization (avg {round(avg_cpu, 2)}%) over the last {days} days.",
                                    "confidence_score": 0.92
                                })

        except ClientError as e:
            logger.warning("idle_instance_scan_error", error=str(e))

        return zombies
