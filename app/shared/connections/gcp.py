from uuid import UUID
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.gcp_connection import GCPConnection
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.exceptions import ResourceNotFoundError


class GCPConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_connection(
        self, connection_id: UUID, tenant_id: UUID
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(GCPConnection).where(
                GCPConnection.id == connection_id, GCPConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ResourceNotFoundError(f"GCP Connection {connection_id} not found")

        adapter = AdapterFactory.get_adapter(connection)
        success = await adapter.verify_connection()
        if success:
            connection.is_active = True
            await self.db.commit()
            return {"status": "success", "message": "GCP connection verified."}
        else:
            failure_message = getattr(adapter, "last_error", None) or (
                "Failed to authenticate with GCP. Check Service Account JSON."
            )
            return {
                "status": "failed",
                "message": failure_message,
            }
