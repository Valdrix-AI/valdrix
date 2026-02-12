from uuid import UUID
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.azure_connection import AzureConnection
from app.shared.adapters.azure import AzureAdapter
from app.shared.core.exceptions import ResourceNotFoundError

class AzureConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_connections(self, tenant_id: UUID) -> list[AzureConnection]:
        result = await self.db.execute(
            select(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def verify_connection(self, connection_id: UUID, tenant_id: UUID) -> dict[str, Any]:
        result = await self.db.execute(
            select(AzureConnection).where(
                AzureConnection.id == connection_id,
                AzureConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ResourceNotFoundError(f"Azure Connection {connection_id} not found")

        adapter = AzureAdapter(connection)
        success = await adapter.verify_connection()
        if success:
            connection.is_active = True
            await self.db.commit()
            return {"status": "success", "message": "Azure connection verified."}
        else:
            return {"status": "failed", "message": "Failed to authenticate with Azure. Check Client ID and Secret."}
