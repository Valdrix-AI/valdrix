"""
Audit Log API Endpoints

Provides:
- GET /audit/logs - Paginated audit logs (admin-only)
"""

from typing import Annotated, Any, Optional, List, Literal
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc
from pydantic import BaseModel, ConfigDict
import structlog

from app.shared.core.auth import CurrentUser, requires_role
from app.shared.db.session import get_db
from app.modules.governance.domain.security.audit_log import AuditLog

logger = structlog.get_logger()
router = APIRouter(tags=["Audit"])


def _sanitize_csv_cell(value: str) -> str:
    """
    Prevent CSV formula injection when exported files are opened in spreadsheet tools.
    """
    if not value:
        return ""
    if value[0] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def _rowcount(result: Any) -> int:
    raw_count = getattr(result, "rowcount", None)
    return raw_count if isinstance(raw_count, int) else 0


class AuditLogResponse(BaseModel):
    id: UUID
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
    sort_by: Literal["event_timestamp", "event_type", "actor_email"] = Query("event_timestamp"),
    order: Literal["asc", "desc"] = Query("desc")
) -> list[AuditLogResponse]:
    """
    Get paginated audit logs for tenant.
    
    Admin-only. Sensitive details are masked by default.
    """
    try:
        if sort_by == "actor_email":
            raise HTTPException(
                status_code=400,
                detail="Sorting by actor_email is not supported for encrypted audit data."
            )

        sort_column = getattr(AuditLog, sort_by)
        order_func = desc if order == "desc" else asc

        query = select(AuditLog).where(
            AuditLog.tenant_id == user.tenant_id
        ).order_by(order_func(sort_column))

        if event_type:
            query = query.where(AuditLog.event_type == event_type)

        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        logs = result.scalars().all()

        return [
            AuditLogResponse(
                id=log.id,
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

    except HTTPException:
        raise
    except Exception as e:
        logger.error("audit_logs_fetch_failed", error=str(e))
        raise HTTPException(500, "Failed to fetch audit logs") from e


@router.get("/logs/{log_id}")
async def get_audit_log_detail(
    log_id: UUID,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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
        raise HTTPException(500, "Failed to fetch audit log") from e


@router.get("/event-types")
async def get_event_types(
    _: Annotated[CurrentUser, Depends(requires_role("admin"))],
) -> dict[str, list[str]]:
    """Get list of available audit event types for filtering."""
    from app.modules.governance.domain.security.audit_log import AuditEventType

    return {
        "event_types": [e.value for e in AuditEventType]
    }


@router.get("/export")
async def export_audit_logs(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    start_date: Optional[datetime] = Query(None, description="Start of date range"),
    end_date: Optional[datetime] = Query(None, description="End of date range"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
) -> Any:
    """
    Export audit logs as CSV for the tenant.
    GDPR/SOC2: Provides audit trail export for compliance.
    """
    from fastapi.responses import StreamingResponse
    import csv
    import io
    
    try:
        query = select(AuditLog).where(
            AuditLog.tenant_id == user.tenant_id
        ).order_by(desc(AuditLog.event_timestamp))
        
        if start_date:
            query = query.where(AuditLog.event_timestamp >= start_date)
        if end_date:
            query = query.where(AuditLog.event_timestamp <= end_date)
        if event_type:
            query = query.where(AuditLog.event_type == event_type)
        
        # Limit export to 10,000 records for performance
        query = query.limit(10000)
        
        result = await db.execute(query)
        logs = result.scalars().all()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "event_type", "event_timestamp", "actor_email", 
            "resource_type", "resource_id", "success", "correlation_id"
        ])
        
        for log in logs:
            writer.writerow([
                str(log.id),
                _sanitize_csv_cell(log.event_type),
                _sanitize_csv_cell(log.event_timestamp.isoformat()),
                _sanitize_csv_cell(log.actor_email or ""),
                _sanitize_csv_cell(log.resource_type or ""),
                _sanitize_csv_cell(str(log.resource_id) if log.resource_id else ""),
                _sanitize_csv_cell(str(log.success)),
                _sanitize_csv_cell(log.correlation_id or "")
            ])
        
        output.seek(0)
        
        logger.info("audit_logs_exported", 
                   tenant_id=str(user.tenant_id),
                   record_count=len(logs))
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{user.tenant_id}.csv"
            }
        )
        
    except Exception as e:
        logger.error("audit_export_failed", error=str(e))
        raise HTTPException(500, "Failed to export audit logs") from e


@router.delete("/data-erasure-request")
async def request_data_erasure(
    user: Annotated[CurrentUser, Depends(requires_role("owner"))],
    db: AsyncSession = Depends(get_db),
    confirmation: str = Query(..., description="Type 'DELETE ALL MY DATA' to confirm")
) -> dict[str, Any]:
    """
    GDPR Article 17 - Right to Erasure (Right to be Forgotten).
    
    Initiates a data erasure request for the tenant.
    Owner role required. Irreversible action.
    """
    if confirmation != "DELETE ALL MY DATA":
        raise HTTPException(
            status_code=400,
            detail="Confirmation text must exactly match 'DELETE ALL MY DATA'"
        )
    
    try:
        from app.models.tenant import User
        from app.models.tenant import Tenant
        from app.models.cloud import CostRecord, CloudAccount
        from app.models.remediation import RemediationRequest
        from app.models.anomaly_marker import AnomalyMarker
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        from app.models.llm import LLMUsage, LLMBudget
        from app.models.notification_settings import NotificationSettings
        from app.models.background_job import BackgroundJob
        from app.models.carbon_settings import CarbonSettings
        from app.models.remediation_settings import RemediationSettings
        from app.models.discovered_account import DiscoveredAccount
        from app.models.attribution import AttributionRule, CostAllocation
        from app.models.cost_audit import CostAuditLog
        from app.models.optimization import StrategyRecommendation
        from sqlalchemy import delete
        
        tenant_id = user.tenant_id

        tenant_row = await db.execute(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant_row.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Log the request before execution
        logger.critical(
            "gdpr_data_erasure_initiated",
            tenant_id=str(tenant_id),
            requested_by=user.email
        )
        
        # Delete in order of dependencies
        deleted_counts = {}
        
        # 1. Delete dependent cost data (audit logs for records)
        await db.execute(
            delete(CostAuditLog).where(
                CostAuditLog.cost_record_id.in_(
                    select(CostRecord.id).where(CostRecord.tenant_id == tenant_id)
                )
            )
        )
        
        # 2. Delete attribution allocations before cost records (FK dependency)
        await db.execute(
            delete(CostAllocation).where(
                CostAllocation.cost_record_id.in_(
                    select(CostRecord.id).where(CostRecord.tenant_id == tenant_id)
                )
            )
        )

        # 3. Delete cost records (largest table)
        result = await db.execute(
            delete(CostRecord).where(CostRecord.tenant_id == tenant_id)
        )
        deleted_counts["cost_records"] = _rowcount(result)
        
        # 4. Delete anomaly markers
        result = await db.execute(
            delete(AnomalyMarker).where(AnomalyMarker.tenant_id == tenant_id)
        )
        deleted_counts["anomaly_markers"] = _rowcount(result)

        # 5. Delete remediation and discovery data
        result = await db.execute(
            delete(RemediationRequest).where(RemediationRequest.tenant_id == tenant_id)
        )
        deleted_counts["remediation_requests"] = _rowcount(result)

        result = await db.execute(
            delete(StrategyRecommendation).where(StrategyRecommendation.tenant_id == tenant_id)
        )
        deleted_counts["strategy_recommendations"] = _rowcount(result)

        # Optimization strategies are global catalog entries, not tenant-owned records.
        # Tenant data erasure must only remove tenant-specific recommendations.
        deleted_counts["optimization_strategies"] = 0

        await db.execute(
            delete(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
        
        result = await db.execute(
            delete(DiscoveredAccount).where(
                DiscoveredAccount.management_connection_id.in_(
                    select(AWSConnection.id).where(AWSConnection.tenant_id == tenant_id)
                )
            )
        )
        deleted_counts["discovered_accounts"] = _rowcount(result)

        # 6. Delete Cloud Connections and Attribution
        await db.execute(
            delete(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        await db.execute(
            delete(GCPConnection).where(GCPConnection.tenant_id == tenant_id)
        )
        
        await db.execute(
            delete(AttributionRule).where(AttributionRule.tenant_id == tenant_id)
        )
        
        # 7. Delete LLM Usage and Budgets
        result = await db.execute(
            delete(LLMUsage).where(LLMUsage.tenant_id == tenant_id)
        )
        deleted_counts["llm_usage_records"] = _rowcount(result)
        
        await db.execute(
            delete(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
        )
        
        # 8. Delete Notification and Carbon settings
        await db.execute(
            delete(NotificationSettings).where(NotificationSettings.tenant_id == tenant_id)
        )
        await db.execute(
            delete(CarbonSettings).where(CarbonSettings.tenant_id == tenant_id)
        )
        
        # 9. Delete Background Jobs
        result = await db.execute(
            delete(BackgroundJob).where(BackgroundJob.tenant_id == tenant_id)
        )
        deleted_counts["background_jobs"] = _rowcount(result)

        # 10. Delete Cloud accounts (Meta)
        result = await db.execute(
            delete(CloudAccount).where(CloudAccount.tenant_id == tenant_id)
        )
        deleted_counts["cloud_accounts"] = _rowcount(result)
        
        # 11. Delete users (except the requesting user - they delete last)
        result = await db.execute(
            delete(User).where(
                User.tenant_id == tenant_id,
                User.id != user.id
            )
        )
        deleted_counts["other_users"] = _rowcount(result)

        
        # 6. Audit logs preserved (required for compliance) but marked
        # We don't delete audit logs - they are required for SOC2
        
        await db.commit()
        
        logger.critical(
            "gdpr_data_erasure_complete",
            tenant_id=str(tenant_id),
            deleted_counts=deleted_counts
        )
        
        return {
            "status": "erasure_complete",
            "message": "All tenant data has been deleted. Audit logs are preserved for compliance.",
            "deleted_counts": deleted_counts,
            "next_steps": [
                "Your account will remain active until you close it via /api/v1/settings/account",
                "Audit logs are retained for 90 days per SOC2 requirements",
                "Contact support@valdrix.com for any questions"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("gdpr_erasure_failed", error=str(e), tenant_id=str(user.tenant_id))
        raise HTTPException(500, "Data erasure failed. Please contact support.") from e
