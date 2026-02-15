from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_connection import PlatformConnection
from app.shared.adapters.platform import PlatformAdapter
from app.shared.core.exceptions import ResourceNotFoundError


class PlatformConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_connections(self, tenant_id: UUID) -> list[PlatformConnection]:
        result = await self.db.execute(
            select(PlatformConnection).where(PlatformConnection.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    async def verify_connection(
        self, connection_id: UUID, tenant_id: UUID
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(PlatformConnection).where(
                PlatformConnection.id == connection_id,
                PlatformConnection.tenant_id == tenant_id,
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            raise ResourceNotFoundError(
                f"Platform Connection {connection_id} not found"
            )

        adapter = PlatformAdapter(connection)
        success = await adapter.verify_connection()
        connection.last_synced_at = datetime.now(timezone.utc)
        connection.is_active = success
        failure_message = adapter.last_error or "Failed to validate platform connector."
        connection.error_message = None if success else failure_message
        await self.db.commit()

        if success:
            return {"status": "success", "message": "Platform connection verified."}
        return {"status": "failed", "message": failure_message}
