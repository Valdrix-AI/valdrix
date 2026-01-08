"""
Zombie Resource Detector & Remediator

Full production implementation with:
1. Zombie detection (unattached volumes, old snapshots, unused EIPs)
2. Approval workflow (pending → approved → executed)
3. Safe delete with backup option
4. Audit trail for compliance

Uses AWS CloudWatch, EC2, and Cost Explorer APIs.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
import boto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.remediation import RemediationRequest, RemediationStatus, RemediationAction

logger = structlog.get_logger()


# Estimated monthly costs for common resources
ESTIMATED_COSTS = {
    "ebs_volume_gb": 0.10,       # $0.10/GB/month for gp2
    "elastic_ip": 3.65,          # $0.005/hour * 730 hours
    "snapshot_gb": 0.05,         # $0.05/GB/month
    "ec2_t3_micro": 7.59,        # t3.micro monthly
    "ec2_t3_small": 15.18,       # t3.small monthly
    "ec2_t3_medium": 30.37,      # t3.medium monthly
    "ec2_m5_large": 69.12,       # m5.large monthly
    "ec2_default": 30.00,        # Default estimate
    "elb": 16.43,                # ALB base cost
}


class ZombieDetector:
    """
    Detects zombie (unused/underutilized) AWS resources.
    
    Usage:
        detector = ZombieDetector()
        zombies = await detector.scan_all()
    """
    
    def __init__(self, region: str = "us-east-1"):
        self.region = region
        self.ec2 = boto3.client("ec2", region_name=region)
        self.cloudwatch = boto3.client("cloudwatch", region_name=region)
        self.elb = boto3.client("elbv2", region_name=region)
    
    async def scan_all(self) -> Dict[str, Any]:
        """
        Scan for all types of zombie resources.
        
        Returns dict with zombies by category and total waste estimate.
        """
        zombies = {
            "unattached_volumes": [],
            "old_snapshots": [],
            "unused_elastic_ips": [],
            "idle_instances": [],
            "total_monthly_waste": Decimal("0"),
            "region": self.region,
            "scanned_at": datetime.utcnow().isoformat(),
        }
        
        try:
            # Scan each category
            zombies["unattached_volumes"] = self._find_unattached_volumes()
            zombies["old_snapshots"] = self._find_old_snapshots()
            zombies["unused_elastic_ips"] = self._find_unused_elastic_ips()
            
            # Calculate total waste
            total = Decimal("0")
            for vol in zombies["unattached_volumes"]:
                total += Decimal(str(vol.get("monthly_cost", 0)))
            for snap in zombies["old_snapshots"]:
                total += Decimal(str(snap.get("monthly_cost", 0)))
            for eip in zombies["unused_elastic_ips"]:
                total += Decimal(str(ESTIMATED_COSTS["elastic_ip"]))
            
            zombies["total_monthly_waste"] = float(round(total, 2))
            
            logger.info(
                "zombie_scan_complete",
                volumes=len(zombies["unattached_volumes"]),
                snapshots=len(zombies["old_snapshots"]),
                eips=len(zombies["unused_elastic_ips"]),
                waste=zombies["total_monthly_waste"],
            )
            
        except ClientError as e:
            logger.error("zombie_scan_failed", error=str(e))
            zombies["error"] = str(e)
        
        return zombies
    
    def _find_unattached_volumes(self) -> List[Dict[str, Any]]:
        """Find EBS volumes not attached to any instance."""
        zombies = []
        
        try:
            response = self.ec2.describe_volumes(
                Filters=[{"Name": "status", "Values": ["available"]}]
            )
            
            for vol in response.get("Volumes", []):
                size_gb = vol.get("Size", 0)
                monthly_cost = size_gb * ESTIMATED_COSTS["ebs_volume_gb"]
                backup_cost = size_gb * ESTIMATED_COSTS["snapshot_gb"]
                
                zombies.append({
                    "resource_id": vol["VolumeId"],
                    "resource_type": "EBS Volume",
                    "size_gb": size_gb,
                    "monthly_cost": round(monthly_cost, 2),
                    "backup_cost_monthly": round(backup_cost, 2),
                    "created": vol["CreateTime"].isoformat(),
                    "recommendation": "Delete if no longer needed",
                    "action": "delete_volume",
                    "supports_backup": True,
                })
        except ClientError as e:
            logger.warning("volume_scan_error", error=str(e))
        
        return zombies
    
    def _find_old_snapshots(self, days_old: int = 90) -> List[Dict[str, Any]]:
        """Find EBS snapshots older than threshold."""
        zombies = []
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        
        try:
            response = self.ec2.describe_snapshots(OwnerIds=["self"])
            
            for snap in response.get("Snapshots", []):
                start_time = snap.get("StartTime")
                if start_time and start_time.replace(tzinfo=None) < cutoff:
                    size_gb = snap.get("VolumeSize", 0)
                    monthly_cost = size_gb * ESTIMATED_COSTS["snapshot_gb"]
                    
                    zombies.append({
                        "resource_id": snap["SnapshotId"],
                        "resource_type": "EBS Snapshot",
                        "size_gb": size_gb,
                        "age_days": (datetime.utcnow() - start_time.replace(tzinfo=None)).days,
                        "monthly_cost": round(monthly_cost, 2),
                        "backup_cost_monthly": 0,
                        "recommendation": "Delete if backup no longer needed",
                        "action": "delete_snapshot",
                        "supports_backup": False,
                    })
        except ClientError as e:
            logger.warning("snapshot_scan_error", error=str(e))
        
        return zombies
    
    def _find_unused_elastic_ips(self) -> List[Dict[str, Any]]:
        """Find Elastic IPs not associated with any instance."""
        zombies = []
        
        try:
            response = self.ec2.describe_addresses()
            
            for addr in response.get("Addresses", []):
                if not addr.get("InstanceId") and not addr.get("NetworkInterfaceId"):
                    zombies.append({
                        "resource_id": addr.get("AllocationId", addr.get("PublicIp")),
                        "resource_type": "Elastic IP",
                        "public_ip": addr.get("PublicIp"),
                        "monthly_cost": ESTIMATED_COSTS["elastic_ip"],
                        "backup_cost_monthly": 0,
                        "recommendation": "Release if not needed",
                        "action": "release_elastic_ip",
                        "supports_backup": False,
                    })
        except ClientError as e:
            logger.warning("eip_scan_error", error=str(e))
        
        return zombies


class RemediationService:
    """
    Manages the remediation approval workflow.
    
    Workflow:
    1. create_request() - User requests remediation
    2. list_pending() - Reviewer sees pending requests  
    3. approve() / reject() - Reviewer takes action
    4. execute() - System executes approved requests
    """
    
    def __init__(self, db: AsyncSession, region: str = "us-east-1"):
        self.db = db
        self.region = region
        self.ec2 = boto3.client("ec2", region_name=region)
    
    async def create_request(
        self,
        tenant_id: UUID,
        user_id: UUID,
        resource_id: str,
        resource_type: str,
        action: RemediationAction,
        estimated_savings: float,
        create_backup: bool = False,
        backup_retention_days: int = 30,
        backup_cost_estimate: float = 0,
    ) -> RemediationRequest:
        """
        Create a new remediation request (pending approval).
        """
        request = RemediationRequest(
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            region=self.region,
            action=action,
            status=RemediationStatus.PENDING,
            estimated_monthly_savings=Decimal(str(estimated_savings)),
            create_backup=create_backup,
            backup_retention_days=backup_retention_days,
            backup_cost_estimate=Decimal(str(backup_cost_estimate)) if backup_cost_estimate else None,
            requested_by_user_id=user_id,
        )
        
        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)
        
        logger.info(
            "remediation_request_created",
            request_id=str(request.id),
            resource=resource_id,
            action=action.value,
            backup=create_backup,
        )
        
        return request
    
    async def list_pending(self, tenant_id: UUID) -> List[RemediationRequest]:
        """List all pending remediation requests for a tenant."""
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.tenant_id == tenant_id)
            .where(RemediationRequest.status == RemediationStatus.PENDING)
            .order_by(RemediationRequest.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def approve(
        self,
        request_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> RemediationRequest:
        """
        Approve a remediation request.
        Does NOT execute yet - that's a separate step for safety.
        """
        result = await self.db.execute(
            select(RemediationRequest).where(RemediationRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
        
        if request.status != RemediationStatus.PENDING:
            raise ValueError(f"Request is {request.status.value}, not pending")
        
        request.status = RemediationStatus.APPROVED
        request.reviewed_by_user_id = reviewer_id
        request.review_notes = notes
        
        await self.db.commit()
        await self.db.refresh(request)
        
        logger.info(
            "remediation_approved",
            request_id=str(request_id),
            reviewer=str(reviewer_id),
        )
        
        return request
    
    async def reject(
        self,
        request_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> RemediationRequest:
        """Reject a remediation request."""
        result = await self.db.execute(
            select(RemediationRequest).where(RemediationRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
        
        request.status = RemediationStatus.REJECTED
        request.reviewed_by_user_id = reviewer_id
        request.review_notes = notes
        
        await self.db.commit()
        await self.db.refresh(request)
        
        logger.info(
            "remediation_rejected",
            request_id=str(request_id),
            reviewer=str(reviewer_id),
        )
        
        return request
    
    async def execute(self, request_id: UUID) -> RemediationRequest:
        """
        Execute an approved remediation request.
        
        If create_backup is True, creates snapshot before deleting volume.
        """
        result = await self.db.execute(
            select(RemediationRequest).where(RemediationRequest.id == request_id)
        )
        request = result.scalar_one_or_none()
        
        if not request:
            raise ValueError(f"Request {request_id} not found")
        
        if request.status != RemediationStatus.APPROVED:
            raise ValueError(f"Request must be approved first (current: {request.status.value})")
        
        request.status = RemediationStatus.EXECUTING
        await self.db.commit()
        
        try:
            # Create backup if requested (for volumes only)
            if request.create_backup and request.action == RemediationAction.DELETE_VOLUME:
                backup_id = await self._create_volume_backup(
                    request.resource_id,
                    request.backup_retention_days,
                )
                request.backup_resource_id = backup_id
            
            # Execute the action
            await self._execute_action(request.resource_id, request.action)
            
            request.status = RemediationStatus.COMPLETED
            logger.info(
                "remediation_executed",
                request_id=str(request_id),
                resource=request.resource_id,
            )
            
        except Exception as e:
            request.status = RemediationStatus.FAILED
            request.execution_error = str(e)[:500]
            logger.error(
                "remediation_failed",
                request_id=str(request_id),
                error=str(e),
            )
        
        await self.db.commit()
        await self.db.refresh(request)
        return request
    
    async def _create_volume_backup(
        self,
        volume_id: str,
        retention_days: int,
    ) -> str:
        """Create a snapshot backup before deleting a volume."""
        try:
            response = self.ec2.create_snapshot(
                VolumeId=volume_id,
                Description=f"Backup before remediation - retain {retention_days} days",
                TagSpecifications=[
                    {
                        "ResourceType": "snapshot",
                        "Tags": [
                            {"Key": "CloudSentinel", "Value": "remediation-backup"},
                            {"Key": "RetentionDays", "Value": str(retention_days)},
                            {"Key": "OriginalVolume", "Value": volume_id},
                        ],
                    }
                ],
            )
            
            backup_id = response["SnapshotId"]
            logger.info(
                "backup_created",
                volume_id=volume_id,
                snapshot_id=backup_id,
            )
            return backup_id
            
        except ClientError as e:
            logger.error("backup_creation_failed", volume_id=volume_id, error=str(e))
            raise
    
    async def _execute_action(
        self,
        resource_id: str,
        action: RemediationAction,
    ) -> None:
        """Execute the actual AWS action."""
        try:
            if action == RemediationAction.DELETE_VOLUME:
                self.ec2.delete_volume(VolumeId=resource_id)
                
            elif action == RemediationAction.DELETE_SNAPSHOT:
                self.ec2.delete_snapshot(SnapshotId=resource_id)
                
            elif action == RemediationAction.RELEASE_ELASTIC_IP:
                self.ec2.release_address(AllocationId=resource_id)
                
            elif action == RemediationAction.STOP_INSTANCE:
                self.ec2.stop_instances(InstanceIds=[resource_id])
                
            elif action == RemediationAction.TERMINATE_INSTANCE:
                self.ec2.terminate_instances(InstanceIds=[resource_id])
                
            else:
                raise ValueError(f"Unknown action: {action}")
                
        except ClientError as e:
            logger.error("aws_action_failed", resource=resource_id, error=str(e))
            raise
