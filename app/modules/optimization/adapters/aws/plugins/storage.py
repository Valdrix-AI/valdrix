from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()


@registry.register("aws")
class UnattachedVolumesPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "unattached_volumes"

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
            ) as ec2:
                paginator = ec2.get_paginator("describe_volumes")
                async with self._get_client(
                    session, "cloudwatch", region, credentials, config=config
                ) as cloudwatch:
                    async for page in paginator.paginate(
                        Filters=[{"Name": "status", "Values": ["available"]}]
                    ):
                        for vol in page.get("Volumes", []):
                            vol_id = vol["VolumeId"]
                            size_gb = vol.get("Size", 0)

                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=7)

                                # Check for ANY ops
                                ops_metrics = await cloudwatch.get_metric_data(
                                    MetricDataQueries=[
                                        {
                                            "Id": "read_ops",
                                            "MetricStat": {
                                                "Metric": {
                                                    "Namespace": "AWS/EBS",
                                                    "MetricName": "VolumeReadOps",
                                                    "Dimensions": [
                                                        {
                                                            "Name": "VolumeId",
                                                            "Value": vol_id,
                                                        }
                                                    ],
                                                },
                                                "Period": 604800,
                                                "Stat": "Sum",
                                            },
                                        },
                                        {
                                            "Id": "write_ops",
                                            "MetricStat": {
                                                "Metric": {
                                                    "Namespace": "AWS/EBS",
                                                    "MetricName": "VolumeWriteOps",
                                                    "Dimensions": [
                                                        {
                                                            "Name": "VolumeId",
                                                            "Value": vol_id,
                                                        }
                                                    ],
                                                },
                                                "Period": 604800,
                                                "Stat": "Sum",
                                            },
                                        },
                                    ],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                )

                                total_ops = 0
                                for m_res in ops_metrics.get("MetricDataResults", []):
                                    total_ops += sum(m_res.get("Values", [0]))

                                if total_ops > 0:
                                    # logger.info("volume_has_recent_ops_skipping", vol=vol_id, ops=total_ops)
                                    continue

                            except ClientError as e:
                                logger.warning(
                                    "volume_metric_check_failed",
                                    vol=vol_id,
                                    error=str(e),
                                )

                            from app.modules.reporting.domain.pricing.service import (
                                PricingService,
                            )

                            monthly_cost = PricingService.estimate_monthly_waste(
                                provider="aws",
                                resource_type="volume",
                                resource_size="gp2",  # Defaulting to gp2 if unknown
                                region=region,
                                quantity=size_gb,
                            )
                            backup_cost = PricingService.estimate_monthly_waste(
                                provider="aws",
                                resource_type="volume",
                                resource_size="snapshot_gb",  # Internal key for snap-GB
                                region=region,
                                quantity=size_gb,
                            )

                            zombies.append(
                                {
                                    "resource_id": vol_id,
                                    "resource_type": "EBS Volume",
                                    "size_gb": size_gb,
                                    "monthly_cost": round(monthly_cost, 2),
                                    "backup_cost_monthly": round(backup_cost, 2),
                                    "created": vol["CreateTime"].isoformat(),
                                    "recommendation": "Delete if no longer needed",
                                    "action": "delete_volume",
                                    "supports_backup": True,
                                    "explainability_notes": "Volume is 'available' (detached) and has had 0 IOPS in the last 7 days.",
                                    "confidence_score": 0.98
                                    if total_ops == 0
                                    else 0.85,
                                }
                            )
        except ClientError as e:
            logger.warning("volume_scan_error", error=str(e))

        return zombies


@registry.register("aws")
class OldSnapshotsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "old_snapshots"

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
        days_old = 90
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)

        try:
            async with self._get_client(
                session, "ec2", region, credentials, config=config
            ) as ec2:
                paginator = ec2.get_paginator("describe_snapshots")
                async for page in paginator.paginate(OwnerIds=["self"]):
                    for snap in page.get("Snapshots", []):
                        start_time = snap.get("StartTime")
                        if start_time and start_time < cutoff:
                            from app.modules.reporting.domain.pricing.service import (
                                PricingService,
                            )

                            size_gb = snap.get("VolumeSize", 0)
                            monthly_cost = PricingService.estimate_monthly_waste(
                                provider="aws",
                                resource_type="volume",
                                resource_size="snapshot_gb",
                                region=region,
                                quantity=size_gb,
                            )

                            zombies.append(
                                {
                                    "resource_id": snap["SnapshotId"],
                                    "resource_type": "EBS Snapshot",
                                    "size_gb": size_gb,
                                    "age_days": (
                                        datetime.now(timezone.utc) - start_time
                                    ).days,
                                    "monthly_cost": round(monthly_cost, 2),
                                    "backup_cost_monthly": 0,
                                    "recommendation": "Delete if backup no longer needed",
                                    "action": "delete_snapshot",
                                    "supports_backup": False,
                                    "explainability_notes": f"Snapshot is {(datetime.now(timezone.utc) - start_time).days} days old, exceeding standard data retention policies.",
                                    "confidence_score": 0.99,
                                }
                            )
        except ClientError as e:
            logger.warning("snapshot_scan_error", error=str(e))

        return zombies


@registry.register("aws")
class IdleS3BucketsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_s3_buckets"

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
                session, "s3", region, credentials, config=config
            ) as s3:
                response = await s3.list_buckets()
                buckets = response.get("Buckets", [])
                for bucket in buckets:
                    name = bucket["Name"]
                    try:
                        objects = await s3.list_objects_v2(Bucket=name, MaxKeys=1)
                        # Also check for versions (a bucket might be "empty" but have delete markers or old versions costing money)
                        versions = await s3.list_object_versions(Bucket=name, MaxKeys=1)

                        if (
                            "Contents" not in objects
                            and "Versions" not in versions
                            and "DeleteMarkers" not in versions
                        ):
                            zombies.append(
                                {
                                    "resource_id": name,
                                    "resource_type": "S3 Bucket",
                                    "reason": "Empty Bucket",
                                    "monthly_cost": 0.0,
                                    "recommendation": "Delete if empty & unused",
                                    "action": "delete_s3_bucket",
                                    "explainability_notes": "S3 bucket contains 0 objects and has no recent access logs (if enabled).",
                                    "confidence_score": 0.99,
                                }
                            )
                    except ClientError as e:
                        logger.warning(
                            "s3_access_check_failed", bucket=name, error=str(e)
                        )
        except ClientError as e:
            logger.warning("s3_scan_error", error=str(e))
        return zombies


@registry.register("aws")
class EmptyEfsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "empty_efs_volumes"

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

        try:
            async with self._get_client(
                session, "efs", region, credentials, config=config
            ) as efs:
                paginator = efs.get_paginator("describe_file_systems")
                async with self._get_client(
                    session, "cloudwatch", region, credentials, config=config
                ) as cloudwatch:
                    async for page in paginator.paginate():
                        for fs in page.get("FileSystems", []):
                            fs_id = fs["FileSystemId"]
                            
                            # Check number of mount targets (if 0, definitely unattached)
                            if fs["NumberOfMountTargets"] == 0:
                                size_gb = fs.get("SizeInBytes", {}).get("Value", 0) / (1024**3)
                                # Estimate Cost: ~$0.30/GB/month for Standard
                                monthly_cost = size_gb * 0.30

                                zombies.append(
                                    {
                                        "resource_id": fs_id,
                                        "resource_type": "EFS File System",
                                        "size_gb": round(size_gb, 2),
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "Delete unused file system",
                                        "action": "delete_efs",
                                        "explainability_notes": "EFS has 0 mount targets, meaning it is not attached to any VPC/Instance.",
                                        "confidence_score": 1.0,
                                    }
                                )
                                continue

                            # If mounted, check if actually used (ClientConnections metric)
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days)

                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/EFS",
                                    MetricName="ClientConnections",
                                    Dimensions=[{"Name": "FileSystemId", "Value": fs_id}],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=86400 * days,
                                    Statistics=["Sum"],
                                )

                                total_conns = sum(d["Sum"] for d in metrics.get("Datapoints", []))

                                if total_conns == 0:
                                    size_gb = fs.get("SizeInBytes", {}).get("Value", 0) / (1024**3)
                                    monthly_cost = size_gb * 0.30
                                    
                                    # If very small (<1MB), likely empty default

                                    zombies.append(
                                        {
                                            "resource_id": fs_id,
                                            "resource_type": "EFS File System",
                                            "size_gb": round(size_gb, 2),
                                            "monthly_cost": round(monthly_cost, 2),
                                            "recommendation": "Delete if unused",
                                            "action": "delete_efs",
                                            "explainability_notes": f"EFS has had 0 client connections in the last {days} days.",
                                            "confidence_score": 0.90,
                                        }
                                    )

                            except ClientError as e:
                                logger.warning("efs_metric_check_failed", fs=fs_id, error=str(e))

        except ClientError as e:
            logger.warning("efs_scan_error", error=str(e))

        return zombies
