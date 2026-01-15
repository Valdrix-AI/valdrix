"""
AWS Connection Service

Handles business logic for AWS account connections, including:
- Generating CloudFormation/Terraform setup templates.
- Verifying IAM role access via STS.
- Managing connection lifecycle.
"""

from uuid import UUID
from datetime import datetime, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.aws_connection import AWSConnection
from app.services.connections.cur_automation import IAMCURManager

logger = structlog.get_logger()

class AWSConnectionService:
    @staticmethod
    def get_setup_templates(external_id: str) -> dict:
        """
        Generate CloudFormation and Terraform templates by reading from standalone files.
        """
        import os
        
        # Base paths for templates
        # We assume they are in the project root relative to this file
        # /app/services/connections/aws.py -> ../../../cloudformation/valdrix-role.yaml
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        cf_path = os.path.join(root_dir, "cloudformation", "valdrix-role.yaml")
        tf_path = os.path.join(root_dir, "terraform", "valdrix-role.tf")

        try:
            with open(cf_path, "r", encoding="utf-8") as f:
                cloudformation_yaml = f.read().replace("!Ref ExternalId", f"'{external_id}'")
            
            with open(tf_path, "r", encoding="utf-8") as f:
                terraform_hcl = f.read().replace("vx-YOUR_EXTERNAL_ID_HERE", external_id)
        except (IOError, OSError) as e:
            logger.error("template_load_failed", error=str(e))
            # Fallback to empty or minimal if files missing (though they shouldn't be)
            cloudformation_yaml = f"# Template load failed: {str(e)}"
            terraform_hcl = f"# Template load failed: {str(e)}"

        return {
            "external_id": external_id,
            "cloudformation_yaml": cloudformation_yaml,
            "terraform_hcl": terraform_hcl,
            "magic_link": (
                f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?"
                f"stackName=ValdrixSecurityAudit&"
                f"templateURL=https://raw.githubusercontent.com/Valdrix-AI/valdrix/main/cloudformation/valdrix-role.yaml&"
                f"param_ExternalId={external_id}"
            ),
            "instructions": (
                "1. Click the '⚡ Launch AWS Stack' button below\n"
                "2. Review the permissions and click 'Create Stack' in AWS console\n"
                "3. Copy the Role ARN from the stack 'Outputs' tab\n"
                "4. Paste the Role ARN below to verify"
            ),
            "permissions_summary": [
                "ce:GetCostAndUsage - Read your cost data",
                "ce:GetCostForecast - View cost predictions",
                "ce:GetTags - Read cost allocation tags",
                "ec2:DescribeInstances - Detect idle EC2 instances",
                "ec2:DescribeVolumes - Detect unattached EBS volumes",
                "ec2:DescribeSnapshots - Detect old snapshots",
                "ec2:DescribeAddresses - Detect unused Elastic IPs",
                "ec2:DescribeNatGateways - Detect underused NAT gateways",
                "elasticloadbalancing:Describe* - Detect orphan load balancers",
                "rds:DescribeDBInstances - Detect idle RDS databases",
                "cloudwatch:GetMetricData - Monitor resource utilization",
            ]
        }

    @staticmethod
    async def verify_role_access(role_arn: str, external_id: str) -> tuple[bool, str | None]:
        """
        Test if we can assume the IAM role (Async).
        Returns: (success, error_message)
        """
        try:
            session = aioboto3.Session()
            async with session.client("sts") as sts_client:
                await sts_client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName="ValdrixVerification",
                    ExternalId=external_id,
                    DurationSeconds=900,
                )
                logger.info("aws_connection_verified", role_arn=role_arn)
                return True, None
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            logger.warning("aws_connection_verification_failed", role_arn=role_arn, error_code=error_code)
            return False, f"{error_code}: {error_message}"

    @classmethod
    async def verify_connection(cls, db: AsyncSession, connection_id: UUID, tenant_id: UUID) -> dict:
        """Fetch connection, verify role access, and update status."""
        result = await db.execute(
            select(AWSConnection).where(
                AWSConnection.id == connection_id,
                AWSConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()

        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        success, error = await cls.verify_role_access(connection.role_arn, connection.external_id)

        connection.status = "active" if success else "error"
        connection.last_verified_at = datetime.now(timezone.utc)
        connection.error_message = error
        await db.commit()

        if success:
            # Trigger CUR Automation if not already active
            if connection.cur_status == "none":
                await cls.setup_cur(db, connection)
            
            return {"status": "active", "message": "Connection verified successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Connection verification failed: {error}"
            )

    @classmethod
    async def setup_cur(cls, db: AsyncSession, connection: AWSConnection):
        """
        Trigger automated S3/CUR setup for a connection.
        """
        manager = IAMCURManager(connection)
        connection.cur_status = "setting_up"
        await db.commit()

        try:
            result = await manager.setup_cur_automation()
            connection.cur_bucket_name = result["bucket_name"]
            connection.cur_report_name = result["report_name"]
            connection.cur_status = "active"
            await db.commit()
            logger.info("cur_automation_triggered", 
                        connection_id=str(connection.id), 
                        bucket=result["bucket_name"])
        except Exception as e:
            connection.cur_status = "error"
            connection.error_message = f"CUR Setup Failed: {str(e)}"
            await db.commit()
            logger.error("cur_automation_trigger_failed", 
                         connection_id=str(connection.id), 
                         error=str(e))
