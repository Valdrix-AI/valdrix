"""
Audit Log API Endpoints

Provides:
- GET /audit/logs - Paginated audit logs (admin-only)
"""

from typing import Annotated, Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict
import structlog

from app.core.auth import CurrentUser, requires_role
from app.db.session import get_db
from app.services.security.audit_log import AuditLog

logger = structlog.get_logger()
router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditLogResponse(BaseModel):
    id: str
    event_type: str
    event_timestamp: datetime
    actor_email: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    success: bool
    correlation_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
):
    """
    Get paginated audit logs for tenant.
    
    Admin-only. Sensitive details are masked by default.
    """
    try:
        query = select(AuditLog).where(
            AuditLog.tenant_id == user.tenant_id
        ).order_by(desc(AuditLog.event_timestamp))

        if event_type:
            query = query.where(AuditLog.event_type == event_type)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        logs = result.scalars().all()

        return [
            AuditLogResponse(
                id=str(log.id),
                event_type=log.event_type,
                event_timestamp=log.event_timestamp,
                actor_email=log.actor_email,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                success=log.success,
                correlation_id=log.correlation_id
            )
            for log in logs
        ]

    except Exception as e:
        logger.error("audit_logs_fetch_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit logs")


@router.get("/logs/{log_id}")
async def get_audit_log_detail(
    log_id: UUID,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
):
    """Get single audit log entry with full details."""
    try:
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.id == log_id,
                AuditLog.tenant_id == user.tenant_id
            )
        )
        log = result.scalar_one_or_none()

        if not log:
            raise HTTPException(404, "Audit log not found")

        return {
            "id": str(log.id),
            "event_type": log.event_type,
            "event_timestamp": log.event_timestamp.isoformat(),
            "actor_id": str(log.actor_id) if log.actor_id else None,
            "actor_email": log.actor_email,
            "actor_ip": log.actor_ip,
            "correlation_id": log.correlation_id,
            "request_method": log.request_method,
            "request_path": log.request_path,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": log.details,  # Already masked by AuditLogger
            "success": log.success,
            "error_message": log.error_message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("audit_log_detail_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit log")


@router.get("/event-types")
async def get_event_types(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
):
    """Get list of available audit event types for filtering."""
    from app.services.security.audit_log import AuditEventType

    return {
        "event_types": [e.value for e in AuditEventType]
    }
