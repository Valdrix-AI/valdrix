from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.shared.adapters.rate_limiter import RateLimiter
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()
cloudwatch_limiter = RateLimiter(
    rate_per_second=1.0
)  # Conservative limit for CloudWatch


@registry.register("aws")
class UnusedElasticIpsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "unused_elastic_ips"

    async def scan(
        self,
        session: aioboto3.Session,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with self._get_client(
                session, "ec2", region, credentials, config=config
            ) as ec2:
                response = await ec2.describe_addresses()

                for addr in response.get("Addresses", []):
                    # SEC: Check AssociationId and NetworkInterfaceId properly
                    # Legitimate EIP usage: instance-attached or NI-attached (including NAT Gateways)
                    is_zombie = (
                        not addr.get("InstanceId")
                        and not addr.get("NetworkInterfaceId")
                        and not addr.get("AssociationId")
                    )

                    if is_zombie:
                        zombies.append(
                            {
                                "resource_id": addr.get(
                                    "AllocationId", addr.get("PublicIp")
                                ),
                                "resource_type": "Elastic IP",
                                "public_ip": addr.get("PublicIp"),
                                "monthly_cost": PricingService.estimate_monthly_waste(
                                    provider="aws", resource_type="ip", region=region
                                ),
                                "backup_cost_monthly": 0,
                                "recommendation": "Release if not needed",
                                "action": "release_elastic_ip",
                                "supports_backup": False,
                                "explainability_notes": "Static IP address is not associated with any running instance, network interface, or association ID.",
                                "confidence_score": 0.99,
                            }
                        )
        except ClientError as e:
            logger.warning("eip_scan_error", error=str(e))

        return zombies


@registry.register("aws")
class IdleInstancesPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_instances"

    async def _get_attribution(
        self,
        session: aioboto3.Session,
        region: str,
        instance_id: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
    ) -> str:
        """
        Governance Layer: Uses CloudTrail to find who launched the instance.
        """
        try:
            async with self._get_client(
                session, "cloudtrail", region, credentials, config=config
            ) as ct:
                response = await ct.lookup_events(
                    LookupAttributes=[
                        {"AttributeKey": "ResourceName", "AttributeValue": instance_id}
                    ],
                    MaxResults=10,
                )
                for event in response.get("Events", []):
                    # We look for the RunInstances event to find the original launcher
                    if event.get("EventName") == "RunInstances":
                        return str(event.get("Username", "Unknown"))
        except Exception as e:
            logger.warning(
                "cloudtrail_lookup_failed", instance_id=instance_id, error=str(e)
            )
        return "Unknown"

    async def scan(
        self,
        session: aioboto3.Session,
        region: str,
        credentials: Dict[str, str] | None = None,
        config: Any = None,
        inventory: Any = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        zombies = []
        instances = []
        cpu_threshold = 2.0  # Tightened from 5% (BE-ZD-3)
        days = 14  # Extended from 7 days (BE-ZD-3)

        # GPU Precision: p3, p4, g4, g5, p5, trn1 etc.
        gpu_families = ["p3", "p4", "g4", "g5", "p5", "trn1", "dl1"]

        try:
            # Phase 1: Use pre-fetched inventory if available (Hybrid Model)
            if inventory and inventory.resources:
                logger.info(
                    "idle_instance_scan_using_inventory", count=len(inventory.resources)
                )
                instance_ids: List[str] = []
                seen_ids = set()
                for res in inventory.resources:
                    res_type = getattr(res, "resource_type", "") or ""
                    res_arn = getattr(res, "arn", "") or ""
                    if (
                        res_type in ("EC2 Instance", "instance")
                        or "instance" in res_arn
                    ):
                        res_id = getattr(res, "id", None)
                        if res_id and res_id not in seen_ids:
                            seen_ids.add(res_id)
                            instance_ids.append(res_id)

                # If we found instances in inventory, we fetch their full details in one batch
                if instance_ids:
                    detailed_instances: List[Dict[str, Any]] = []
                    async with self._get_client(
                        session, "ec2", region, credentials, config=config
                    ) as ec2:
                        # Batch by 50 to avoid URI length issues
                        for i in range(0, len(instance_ids), 50):
                            batch_ids = instance_ids[i : i + 50]
                            response = await ec2.describe_instances(
                                InstanceIds=batch_ids
                            )
                            for reservation in response.get("Reservations", []):
                                for instance in reservation.get("Instances", []):
                                    if instance["State"]["Name"] != "running":
                                        continue

                                    tags = {
                                        t["Key"].lower(): t["Value"].lower()
                                        for t in instance.get("Tags", [])
                                    }
                                    if any(
                                        k in ["workload", "type"]
                                        and any(
                                            v in tags[k]
                                            for v in ["batch", "scheduled", "cron"]
                                        )
                                        for k in tags
                                    ):
                                        continue
                                    if any(
                                        "batch" in k or "batch" in tags[k] for k in tags
                                    ):
                                        continue

                                    instance_type = instance.get(
                                        "InstanceType", "unknown"
                                    )
                                    detailed_instances.append(
                                        {
                                            "id": instance["InstanceId"],
                                            "type": instance_type,
                                            "is_gpu": any(
                                                fam in instance_type
                                                for fam in gpu_families
                                            ),
                                            "launch_time": instance.get("LaunchTime"),
                                            "tags": tags,
                                        }
                                    )

                    instances = detailed_instances
            else:
                # Fallback to standard broad scan
                async with self._get_client(
                    session, "ec2", region, credentials, config=config
                ) as ec2:
                    paginator = ec2.get_paginator("describe_instances")
                    async for page in paginator.paginate(
                        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                    ):
                        for reservation in page.get("Reservations", []):
                            for instance in reservation.get("Instances", []):
                                # BE-ZD-3: Skip instances with "batch", "scheduled", or "cron" in tags
                                tags = {
                                    t["Key"].lower(): t["Value"].lower()
                                    for t in instance.get("Tags", [])
                                }
                                if any(
                                    k in ["workload", "type"]
                                    and any(
                                        v in tags[k]
                                        for v in ["batch", "scheduled", "cron"]
                                    )
                                    for k in tags
                                ):
                                    continue
                                if any(
                                    "batch" in k or "batch" in tags[k] for k in tags
                                ):
                                    continue

                                instance_type = instance.get("InstanceType", "unknown")
                                is_gpu = any(
                                    fam in instance_type for fam in gpu_families
                                )

                                instances.append(
                                    {
                                        "id": instance["InstanceId"],
                                        "type": instance_type,
                                        "is_gpu": is_gpu,
                                        "launch_time": instance.get("LaunchTime"),
                                        "tags": tags,
                                    }
                                )

            if not instances:
                return []

            # Phase 3: CUR-Based Idle Detection (Zero API Cost)
            # If CUR records are available, use them instead of CloudWatch
            cur_records = kwargs.get("cur_records")
            if cur_records:
                from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer

                analyzer = CURUsageAnalyzer(cur_records)
                cur_zombies = analyzer.find_low_usage_instances(days=days)
                logger.info("idle_instance_detection_via_cur", count=len(cur_zombies))
                return cur_zombies

            # Fallback: CloudWatch-Based Detection (API Cost to Customer)
            logger.warning(
                "idle_instance_detection_cloudwatch_fallback",
                reason="CUR data not available, using CloudWatch",
            )

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            async with self._get_client(
                session, "cloudwatch", region, credentials, config=config
            ) as cloudwatch:
                # Batch metrics in 500-instance chunks (AWS limit)
                for i in range(0, len(instances), 500):
                    # BE-ZD-2: Rate limiting for CloudWatch queries
                    await cloudwatch_limiter.acquire()

                    batch = instances[i : i + 500]
                    queries = []
                    for idx, inst in enumerate(batch):
                        queries.append(
                            {
                                "Id": f"m{idx}",
                                "MetricStat": {
                                    "Metric": {
                                        "Namespace": "AWS/EC2",
                                        "MetricName": "CPUUtilization",
                                        "Dimensions": [
                                            {"Name": "InstanceId", "Value": inst["id"]}
                                        ],
                                    },
                                    "Period": 86400 * days,
                                    "Stat": "Average",
                                },
                            }
                        )

                    results = await cloudwatch.get_metric_data(
                        MetricDataQueries=queries,
                        StartTime=start_time,
                        EndTime=end_time,
                    )

                    # Map results back to instances
                    for idx, inst in enumerate(batch):
                        res = next(
                            (
                                r
                                for r in results.get("MetricDataResults", [])
                                if r["Id"] == f"m{idx}"
                            ),
                            None,
                        )
                        if res and res.get("Values"):
                            avg_cpu = res["Values"][0]

                            # Decision logic: GPU instances are higher priority "Zombies"
                            # If it's a GPU instance, even slightly higher CPU might still be a zombie if under-utilized
                            threshold = (
                                cpu_threshold * 1.5 if inst["is_gpu"] else cpu_threshold
                            )

                            if avg_cpu < threshold:
                                monthly_cost = PricingService.estimate_monthly_waste(
                                    provider="aws",
                                    resource_type="instance",
                                    resource_size=inst["type"],
                                    region=region,
                                )

                                # Governance: Get Attribution
                                owner = await self._get_attribution(
                                    session, region, inst["id"], credentials, config
                                )

                                zombies.append(
                                    {
                                        "resource_id": inst["id"],
                                        "resource_type": "EC2 Instance",
                                        "instance_type": inst["type"],
                                        "is_gpu": inst["is_gpu"],
                                        "owner": owner,
                                        "avg_cpu_percent": round(avg_cpu, 2),
                                        "monthly_cost": round(monthly_cost, 2),
                                        "launch_time": inst["launch_time"].isoformat()
                                        if inst["launch_time"]
                                        else "",
                                        "recommendation": "Stop or terminate if not needed",
                                        "action": "stop_instance",
                                        "supports_backup": True,
                                        "explainability_notes": f"Instance ({inst['type']}) has shown extremely low CPU utilization (avg {round(avg_cpu, 2)}%) over a 14-day analysis period. {'HIGH PRIORITY: Expensive GPU instance detected.' if inst['is_gpu'] else ''} Launched by: {owner}.",
                                        "confidence_score": 0.99
                                        if inst["is_gpu"]
                                        else 0.98,
                                    }
                                )

        except ClientError as e:
            logger.warning("idle_instance_scan_error", error=str(e))

        return zombies
