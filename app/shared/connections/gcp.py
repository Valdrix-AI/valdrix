from uuid import UUID
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.gcp_connection import GCPConnection
import structlog

logger = structlog.get_logger()

from app.shared.adapters.gcp import GCPAdapter
from app.shared.connections.oidc import OIDCService

class GCPConnectionService:
    """
    Manages GCP Workload Identity Federation and Service Account connections.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_connection(self, connection_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Verifies GCP project access."""
        result = await self.db.execute(
            select(GCPConnection).where(
                GCPConnection.id == connection_id,
                GCPConnection.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        if not connection:
            return {"status": "error", "message": "Connection not found"}

        is_valid = False
        error = None

        if connection.auth_method == "workload_identity":
            is_valid, error = await OIDCService.verify_gcp_access(connection.project_id, str(tenant_id))
        else:
            # Service Account JSON
            adapter = GCPAdapter(connection)
            is_valid = await adapter.verify_connection()
            if not is_valid:
                error = "Service account credentials invalid or insufficient permissions"

        if is_valid:
            connection.is_active = True
            await self.db.commit()
            return {"status": "active", "project_id": connection.project_id}
        else:
            connection.is_active = False
            await self.db.commit()
            return {"status": "error", "message": error or "Verification failed"}
