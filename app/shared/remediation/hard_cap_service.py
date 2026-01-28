from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import structlog
from app.models.aws_connection import AWSConnection
from app.models.tenant import Tenant
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.core.config import get_settings

logger = structlog.get_logger()

class BudgetHardCapService:
    """
    Enforces a 'Hard Cap' by taking destructive or restrictive actions 
    when a tenant's budget is dangerously exceeded.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enforce_hard_cap(self, tenant_id: UUID):
        """
        Example action: Detach all roles or deactivate connections.
        In a production FinOps tool, this might revoke STS role trust.
        """
        logger.warning("enforcing_hard_cap", tenant_id=str(tenant_id))
        
        # Mark connections as inactive/suspended
        await self.db.execute(
            update(AWSConnection)
            .where(AWSConnection.tenant_id == tenant_id)
            .values(status="suspended")
        )
        
        # Deactivate tenant globally
        await self.db.execute(
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(is_active=False)
        )
        
        await self.db.commit()
        logger.info("hard_cap_enforcement_complete", tenant_id=str(tenant_id))
