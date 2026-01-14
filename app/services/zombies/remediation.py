"""
Remediation Service - Approval Workflow for Zombie Resource Cleanup

Manages the remediation approval workflow:
1. create_request() - User requests remediation  
2. list_pending() - Reviewer sees pending requests
3. approve() / reject() - Reviewer takes action
4. execute() - System executes approved requests
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID
import aioboto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.models.remediation import RemediationRequest, RemediationStatus, RemediationAction

logger = structlog.get_logger()


class RemediationService:
    """
    Manages the remediation approval workflow.

    Workflow:
    1. create_request() - User requests remediation
    2. list_pending() - Reviewer sees pending requests
    3. approve() / reject() - Reviewer takes action
    4. execute() - System executes approved requests
    """

    def __init__(self, db: AsyncSession, region: str = "us-east-1", credentials: Dict[str, str] = None):
        self.db = db
        self.region = region
        self.credentials = credentials
        self.session = aioboto3.Session()

    async def _get_client(self, service_name: str):
        """Helper to get aioboto3 client with optional credentials."""
        kwargs = {"region_name": self.region}
        if self.credentials:
            kwargs.update({
                "aws_access_key_id": self.credentials["AccessKeyId"],
                "aws_secret_access_key": self.credentials["SecretAccessKey"],
                "aws_session_token": self.credentials["SessionToken"],
            })
        return self.session.client(service_name, **kwargs)

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
        confidence_score: Optional[float] = None,
        explainability_notes: Optional[str] = None,
    ) -> RemediationRequest:
        """Create a new remediation request (pending approval)."""
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
        tenant_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> RemediationRequest:
        """
        Approve a remediation request.
        Does NOT execute yet - that's a separate step for safety.
        """
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
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
        tenant_id: UUID,
        reviewer_id: UUID,
        notes: Optional[str] = None,
    ) -> RemediationRequest:
        """Reject a remediation request."""
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
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

    async def execute(self, request_id: UUID, tenant_id: UUID) -> RemediationRequest:
        """
        Execute an approved remediation request.

        If create_backup is True, creates snapshot before deleting volume.
        """
        result = await self.db.execute(
            select(RemediationRequest)
            .where(RemediationRequest.id == request_id)
            .where(RemediationRequest.tenant_id == tenant_id)
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
            async with await self._get_client("ec2") as ec2:
                response = await ec2.create_snapshot(
                    VolumeId=volume_id,
                    Description=f"Backup before remediation - retain {retention_days} days",
                    TagSpecifications=[
                        {
                            "ResourceType": "snapshot",
                            "Tags": [
                                {"Key": "Valdrix", "Value": "remediation-backup"},
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
                async with await self._get_client("ec2") as ec2:
                    await ec2.delete_volume(VolumeId=resource_id)

            elif action == RemediationAction.DELETE_SNAPSHOT:
                async with await self._get_client("ec2") as ec2:
                    await ec2.delete_snapshot(SnapshotId=resource_id)

            elif action == RemediationAction.RELEASE_ELASTIC_IP:
                async with await self._get_client("ec2") as ec2:
                    await ec2.release_address(AllocationId=resource_id)

            elif action == RemediationAction.STOP_INSTANCE:
                async with await self._get_client("ec2") as ec2:
                    await ec2.stop_instances(InstanceIds=[resource_id])

            elif action == RemediationAction.TERMINATE_INSTANCE:
                async with await self._get_client("ec2") as ec2:
                    await ec2.terminate_instances(InstanceIds=[resource_id])

            elif action == RemediationAction.DELETE_S3_BUCKET:
                async with await self._get_client("s3") as s3:
                    await s3.delete_bucket(Bucket=resource_id)

            elif action == RemediationAction.DELETE_ECR_IMAGE:
                repo, digest = resource_id.split("@")
                async with await self._get_client("ecr") as ecr:
                    await ecr.batch_delete_image(
                        repositoryName=repo,
                        imageIds=[{'imageDigest': digest}]
                    )

            elif action == RemediationAction.DELETE_SAGEMAKER_ENDPOINT:
                async with await self._get_client("sagemaker") as sagemaker:
                    await sagemaker.delete_endpoint(EndpointName=resource_id)
                    await sagemaker.delete_endpoint_config(EndpointConfigName=resource_id)

            elif action == RemediationAction.DELETE_REDSHIFT_CLUSTER:
                async with await self._get_client("redshift") as redshift:
                    await redshift.delete_cluster(
                        ClusterIdentifier=resource_id,
                        SkipFinalClusterSnapshot=True
                    )

            elif action == RemediationAction.DELETE_LOAD_BALANCER:
                async with await self._get_client("elbv2") as elb:
                    await elb.delete_load_balancer(LoadBalancerArn=resource_id)

            elif action == RemediationAction.STOP_RDS_INSTANCE:
                async with await self._get_client("rds") as rds:
                    await rds.stop_db_instance(DBInstanceIdentifier=resource_id)

            elif action == RemediationAction.DELETE_RDS_INSTANCE:
                async with await self._get_client("rds") as rds:
                    await rds.delete_db_instance(
                        DBInstanceIdentifier=resource_id,
                        SkipFinalSnapshot=True
                    )

            elif action == RemediationAction.DELETE_NAT_GATEWAY:
                async with await self._get_client("ec2") as ec2:
                    await ec2.delete_nat_gateway(NatGatewayId=resource_id)

            else:
                raise ValueError(f"Unknown action: {action}")

        except ClientError as e:
            logger.error("aws_action_failed", resource=resource_id, error=str(e))
            raise
