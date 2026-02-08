"""
AWS Medium-Priority Zombie Detection Plugins

Detects commonly overlooked waste:
- Stopped EC2 instances still paying for EBS storage
- Unused Lambda functions (clutter)
- Orphan VPC Endpoints (~$7.30/month each)
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry

logger = structlog.get_logger()


@registry.register("aws")
class StoppedInstancesWithEbsPlugin(ZombiePlugin):
    """
    Detects stopped EC2 instances that still have attached EBS volumes.
    Users often forget that stopped instances still incur EBS storage costs.
    """
    
    @property
    def category_key(self) -> str:
        return "stopped_instances_with_ebs"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] = None, 
        config: Any = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        zombies = []
        days_stopped_threshold = 7
        
        try:
            async with self._get_client(session, "ec2", region, credentials, config=config) as ec2:
                # Find stopped instances
                paginator = ec2.get_paginator("describe_instances")
                async for page in paginator.paginate(
                    Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
                ):
                    for reservation in page.get("Reservations", []):
                        for instance in reservation.get("Instances", []):
                            instance_id = instance["InstanceId"]
                            instance_type = instance.get("InstanceType", "unknown")
                            
                            # Calculate days stopped (using state transition reason)
                            state_reason = instance.get("StateTransitionReason", "")
                            days_stopped = 0
                            
                            # Parse date from state reason if available
                            # Format: "User initiated (YYYY-MM-DD HH:MM:SS GMT)"
                            days_stopped = 30  # Default if unparseable or missing
                            if "(" in state_reason and ")" in state_reason:
                                try:
                                    date_str = state_reason.split("(")[1].split(")")[0]
                                    # Handle various date formats
                                    for fmt in ["%Y-%m-%d %H:%M:%S GMT", "%Y-%m-%d"]:
                                        try:
                                            stop_time = datetime.strptime(date_str, fmt)
                                            stop_time = stop_time.replace(tzinfo=timezone.utc)
                                            days_stopped = (datetime.now(timezone.utc) - stop_time).days
                                            break
                                        except ValueError:
                                            continue
                                    else:
                                        days_stopped = 30
                                except (IndexError, ValueError):
                                    days_stopped = 30  # Assume old if can't parse
                            
                            # Get attached EBS volumes
                            block_devices = instance.get("BlockDeviceMappings", [])
                            volume_ids = [
                                bd["Ebs"]["VolumeId"] 
                                for bd in block_devices 
                                if "Ebs" in bd
                            ]
                            
                            if days_stopped >= days_stopped_threshold and volume_ids:
                                # Calculate EBS cost
                                total_ebs_cost = 0.0
                                total_gb = 0
                                
                                try:
                                    vol_response = await ec2.describe_volumes(VolumeIds=volume_ids)
                                    for vol in vol_response.get("Volumes", []):
                                        size_gb = vol.get("Size", 0)
                                        total_gb += size_gb
                                        # Approximate cost: $0.10/GB-month for gp2/gp3
                                        total_ebs_cost += size_gb * 0.10
                                except ClientError:
                                    total_ebs_cost = len(volume_ids) * 10.0  # Assume 100GB avg
                                
                                # Get instance name from tags
                                tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
                                instance_name = tags.get("Name", instance_id)
                                
                                zombies.append({
                                    "resource_id": instance_id,
                                    "resource_name": instance_name,
                                    "resource_type": "Stopped EC2 Instance",
                                    "instance_type": instance_type,
                                    "days_stopped": days_stopped,
                                    "attached_volumes": len(volume_ids),
                                    "total_ebs_gb": total_gb,
                                    "monthly_cost": round(total_ebs_cost, 2),
                                    "recommendation": "Instance is stopped but EBS volumes are still incurring charges. Consider creating AMI and terminating.",
                                    "action": "terminate_instance",
                                    "supports_backup": True,
                                    "confidence_score": 0.88,
                                    "explainability_notes": f"Instance '{instance_name}' has been stopped for {days_stopped} days with {len(volume_ids)} attached volumes ({total_gb} GB).",
                                    "detection_method": "api-scan"
                                })
                                
        except ClientError as e:
            logger.warning("stopped_instances_scan_error", error=str(e))
        
        return zombies


@registry.register("aws")
class UnusedLambdaPlugin(ZombiePlugin):
    """
    Detects Lambda functions that haven't been invoked recently.
    While Lambda itself is pay-per-use, unused functions create clutter
    and potential security risks from outdated dependencies.
    """
    
    @property
    def category_key(self) -> str:
        return "unused_lambda_functions"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] = None, 
        config: Any = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        zombies = []
        days_threshold = 30  # Functions not invoked in 30 days
        
        try:
            async with self._get_client(session, "lambda", region, credentials, config=config) as lambda_client:
                async with self._get_client(session, "cloudwatch", region, credentials, config=config) as cloudwatch:
                    paginator = lambda_client.get_paginator("list_functions")
                    async for page in paginator.paginate():
                        for func in page.get("Functions", []):
                            func_name = func["FunctionName"]
                            runtime = func.get("Runtime", "unknown")
                            memory_mb = func.get("MemorySize", 128)
                            
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days_threshold)
                                
                                # Check invocation count
                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/Lambda",
                                    MetricName="Invocations",
                                    Dimensions=[{"Name": "FunctionName", "Value": func_name}],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=86400 * days_threshold,
                                    Statistics=["Sum"]
                                )
                                
                                datapoints = metrics.get("Datapoints", [])
                                total_invocations = sum(d.get("Sum", 0) for d in datapoints)
                                
                                if total_invocations == 0:
                                    zombies.append({
                                        "resource_id": func_name,
                                        "resource_type": "Lambda Function",
                                        "runtime": runtime,
                                        "memory_mb": memory_mb,
                                        "invocations_last_30_days": 0,
                                        "monthly_cost": 0.00,  # No invocations = no cost
                                        "recommendation": "Function has zero invocations. Consider deleting to reduce clutter.",
                                        "action": "delete_lambda_function",
                                        "confidence_score": 0.90,
                                        "explainability_notes": f"Lambda function '{func_name}' has had 0 invocations in the last {days_threshold} days.",
                                        "detection_method": "cloudwatch-metrics"
                                    })
                            except ClientError as e:
                                logger.warning("lambda_metric_fetch_failed", function=func_name, error=str(e))
                                
        except ClientError as e:
            logger.warning("lambda_scan_error", error=str(e))
        
        return zombies


@registry.register("aws")
class OrphanVpcEndpointsPlugin(ZombiePlugin):
    """
    Detects VPC Endpoints with no traffic.
    Interface VPC Endpoints cost ~$7.30/month per AZ even when unused.
    """
    
    @property
    def category_key(self) -> str:
        return "orphan_vpc_endpoints"

    async def scan(
        self, 
        session: aioboto3.Session, 
        region: str, 
        credentials: Dict[str, str] = None, 
        config: Any = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        zombies = []
        days = 7
        
        try:
            async with self._get_client(session, "ec2", region, credentials, config=config) as ec2:
                async with self._get_client(session, "cloudwatch", region, credentials, config=config) as cloudwatch:
                    paginator = ec2.get_paginator("describe_vpc_endpoints")
                    async for page in paginator.paginate():
                        for endpoint in page.get("VpcEndpoints", []):
                            endpoint_id = endpoint["VpcEndpointId"]
                            endpoint_type = endpoint.get("VpcEndpointType", "")
                            service_name = endpoint.get("ServiceName", "unknown")
                            
                            # Only check Interface endpoints (Gateway endpoints are free)
                            if endpoint_type != "Interface":
                                continue
                            
                            # Count AZs for cost calculation
                            subnet_ids = endpoint.get("SubnetIds", [])
                            num_azs = len(subnet_ids) if subnet_ids else 1
                            
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days)
                                
                                # Check bytes processed
                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/PrivateLinkEndpoints",
                                    MetricName="BytesProcessed",
                                    Dimensions=[{"Name": "VPC Endpoint Id", "Value": endpoint_id}],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=604800,
                                    Statistics=["Sum"]
                                )
                                
                                datapoints = metrics.get("Datapoints", [])
                                total_bytes = sum(d.get("Sum", 0) for d in datapoints)
                                
                                if total_bytes == 0:
                                    # ~$7.30/month per AZ for interface endpoints
                                    monthly_cost = 7.30 * num_azs
                                    
                                    zombies.append({
                                        "resource_id": endpoint_id,
                                        "resource_type": "VPC Endpoint",
                                        "endpoint_type": endpoint_type,
                                        "service_name": service_name.split(".")[-1],  # Extract service name
                                        "num_azs": num_azs,
                                        "bytes_processed": 0,
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "VPC Endpoint has no traffic. Consider deleting.",
                                        "action": "delete_vpc_endpoint",
                                        "confidence_score": 0.88,
                                        "explainability_notes": f"Interface VPC Endpoint for {service_name.split('.')[-1]} has processed 0 bytes in {days} days.",
                                        "detection_method": "cloudwatch-metrics"
                                    })
                            except ClientError as e:
                                logger.warning("vpc_endpoint_metric_fetch_failed", endpoint=endpoint_id, error=str(e))
                                
        except ClientError as e:
            logger.warning("vpc_endpoint_scan_error", error=str(e))
        
        return zombies
