from uuid import UUID
from typing import Type, TypeVar
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.exceptions import ResourceNotFoundError

T = TypeVar("T")

class BaseService:
    """
    Base class for all domain services.
    Enforces pattern BE-SEC-02: Strict Tenant Isolation in the service layer.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    def _scoped_query(self, model: Type[T], tenant_id: UUID):
        """Standardized query builder with tenant isolation."""
        # Note: If the model doesn't have tenant_id, this will fail fast.
        # This is strictly for multi-tenant models.
        return select(model).where(model.tenant_id == tenant_id)

    async def get_by_id(self, model: Type[T], id: UUID, tenant_id: UUID, lock: bool = False) -> T:
        """Fetch a single record by ID with strict tenant enforcement."""
        stmt = self._scoped_query(model, tenant_id).where(model.id == id)
        if lock:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()
        
        if not record:
            model_name = model.__name__ if hasattr(model, "__name__") else "Resource"
            raise ResourceNotFoundError(f"{model_name} {id} not found for this tenant.")
            
        return record
