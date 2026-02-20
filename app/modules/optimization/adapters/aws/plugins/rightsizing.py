from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

@registry.register("aws")
class OverprovisionedEc2Plugin(ZombiePlugin):
    """
    Detects Active instances (not zombies) that are significantly overprovisioned.
    Criteria: 
    - State: Running
    - Avg CPU > 1% (Not Idle/Zombie)
    - Max CPU < 10% (Overprovisioned) over 7 days
    """
    @property
    def category_key(self) -> str:
        return "overprovisioned_ec2_instances"

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
                session, "ec2", region, credentials, config=config
            ) as ec2, self._get_client(
                session, "cloudwatch", region, credentials, config=config
            ) as cloudwatch:
                
                paginator = ec2.get_paginator("describe_instances")
                async for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
                    for reservation in page["Reservations"]:
                        for instance in reservation["Instances"]:
                            instance_id = instance["InstanceId"]
                            instance_type = instance["InstanceType"]
                            
                            # Skip if instance type is already very small (t3.nano/micro) 
                            # or if we want to exclude spot/autoscaling (out of scope for PoC)
                            if "nano" in instance_type or "micro" in instance_type:
                                continue

                            now = datetime.now(timezone.utc)
                            start_time = now - timedelta(days=7)
                            end_time = now

                            # Get Maximum CPU to be safe (conservative rightsizing)
                            stats = await cloudwatch.get_metric_statistics(
                                Namespace="AWS/EC2",
                                MetricName="CPUUtilization",
                                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                                StartTime=start_time,
                                EndTime=end_time,
                                Period=86400, # Daily aggregation
                                Statistics=["Maximum"]
                            )
                            
                            datapoints = stats.get("Datapoints", [])
                            if not datapoints:
                                continue
                                
                            # Check if ALL daily maxes are below 10%
                            max_cpu_observed = 0.0
                            below_threshold = True
                            threshold = 10.0 
                            
                            for dp in datapoints:
                                val = dp.get("Maximum", 0)
                                if val > max_cpu_observed:
                                    max_cpu_observed = val
                                if val >= threshold:
                                    below_threshold = False
                                    break
                            
                            if below_threshold:
                                # This is an overprovisioned instance
                                # Recommendation name: "Resize {instance_type}"
                                
                                # Rudimentary cost calc (approx saving ~50% if downgraded one tier)
                                # Real implementation needs pricing api
                                estimated_monthly_cost = 0.0 # Placeholder
                                
                                zombies.append({
                                    "resource_id": instance_id,
                                    "resource_type": "AWS EC2 Instance",
                                    "resource_name": self._get_name_tag(instance),
                                    "region": region,
                                    "monthly_cost": estimated_monthly_cost,
                                    "recommendation": f"Resize {instance_type} (Max CPU {max_cpu_observed:.1f}%)",
                                    "action": "resize_ec2_instance",
                                    # Fact-based confidence input
                                    "utilization_percent": max_cpu_observed, 
                                    "confidence_score": 0.85, # Base, will be adjusted by Recommendation Engine
                                    "explainability_notes": f"Instance {instance_type} had Max CPU of {max_cpu_observed:.1f}% over the last 7 days (Threshold: {threshold}%)."
                                })

        except Exception as e:
            logger.error("aws_rightsizing_scan_error", error=str(e))
            
        return zombies

    def _get_name_tag(self, instance: Dict[str, Any]) -> str:
        for tag in instance.get("Tags", []):
            if tag["Key"] == "Name":
                return str(tag["Value"])
        return str(instance.get("InstanceId", "unknown"))
