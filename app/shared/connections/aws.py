from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog
from app.models.aws_connection import AWSConnection
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.core.exceptions import ResourceNotFoundError, AdapterError

logger = structlog.get_logger()

class AWSConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def get_setup_templates(external_id: str) -> dict:
        """
        Returns CloudFormation and Terraform snippets for provisioning the Valdrix role.
        """
        # Simplistic implementation for now, usually reads from files or templates
        return {
            "external_id": external_id,
            "cloudformation": f"https://valdrix-public.s3.amazonaws.com/templates/valdrix-role.yaml?external_id={external_id}",
            "terraform": f"module \"valdrix_connection\" {{ source = \"valdrix/aws-connection\" external_id = \"{external_id}\" }}",
            "magic_link": f"https://app.valdrix.ai/onboard/aws?external_id={external_id}"
        }

    async def verify_connection(self, connection_id: UUID, tenant_id: UUID) -> dict:
        """
        Verifies that the STS AssumeRole works for the given connection.
        """
        result = await self.db.execute(
            select(AWSConnection).where(
                AWSConnection.id == connection_id,
                AWSConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ResourceNotFoundError(f"AWS Connection {connection_id} not found")

        adapter = MultiTenantAWSAdapter(connection)
        try:
            success = await adapter.verify_connection()
            if success:
                connection.status = "active"
                await self.db.commit()
                return {"status": "success", "message": "Connection verified and active."}
            else:
                connection.status = "error"
                await self.db.commit()
                return {"status": "failed", "message": "Failed to assume role. Check IAM policy and Trust Relationship."}
        except AdapterError as e:
            connection.status = "error"
            await self.db.commit()
            return {"status": "error", "message": str(e), "code": e.code}
        except Exception as e:
            logger.error("aws_verification_unexpected_error", error=str(e), connection_id=str(connection_id))
            return {"status": "error", "message": "An unexpected error occurred during verification."}
