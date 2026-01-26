from uuid import UUID
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.azure_connection import AzureConnection
import structlog

logger = structlog.get_logger()

from app.shared.adapters.azure import AzureAdapter

class AzureConnectionService:
    """
    Manages Azure Workload Identity and Service Principal connections.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_connections(self, tenant_id: UUID) -> List[AzureConnection]:
        """Lists all Azure connections for a tenant."""
        result = await self.db.execute(
            select(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        return result.scalars().all()

    async def verify_connection(self, connection_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Verifies Azure Application registration and subscription access."""
        result = await self.db.execute(
            select(AzureConnection).where(
                AzureConnection.id == connection_id,
                AzureConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            return {"status": "error", "message": "Connection not found"}

        # Delegate verification to adapter
        adapter = AzureAdapter(connection)
        is_valid = await adapter.verify_connection()
        
        if is_valid:
            connection.is_active = True
            await self.db.commit()
            return {"status": "active", "subscription_id": connection.subscription_id}
        else:
            from fastapi import HTTPException
            connection.is_active = False
            await self.db.commit()
            raise HTTPException(status_code=400, detail="Failed to verify Azure connection credentials")
