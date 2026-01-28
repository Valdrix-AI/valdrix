from fastapi import APIRouter, Header, HTTPException, Request, Depends
from app.shared.core.config import get_settings
from app.shared.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
import structlog
from datetime import date
from uuid import UUID
from app.shared.core.rate_limit import auth_limit

router = APIRouter(tags=["Admin Utilities"])
logger = structlog.get_logger()

async def validate_admin_key(
    request: Request,
    x_admin_key: str = Header(..., alias="X-Admin-Key")
):
    """Dependency to validate the admin API key with production hardening."""
    settings = get_settings()

    if not settings.ADMIN_API_KEY:
        logger.error("admin_key_not_configured")
        raise HTTPException(
            status_code=503,
            detail="Admin endpoint not configured. Set ADMIN_API_KEY."
        )

    # Item 11: Prevent weak keys in production
    if settings.ENVIRONMENT == "production" and len(settings.ADMIN_API_KEY) < 32:
        logger.critical("admin_key_too_weak_for_production")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_API_KEY must be at least 32 characters in production."
        )

    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        # Item 11: Audit failed admin access attempts
        from app.shared.core.logging import audit_log
        audit_log("admin_auth_failed", "admin_portal", str(getattr(request.state, 'tenant_id', 'unknown')), 
                  {"path": request.url.path, "ip": request.client.host})
        
        logger.warning("admin_auth_failed", ip=request.client.host)
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return True

@router.post("/trigger-analysis")
@auth_limit # Item 11: Rate limit admin key checks
async def trigger_analysis(
    request: Request,
    _: bool = Depends(validate_admin_key)
):
    """Manually trigger a scheduled analysis job."""

    logger.info("manual_trigger_requested")
    # Access scheduler from app state (passed via request.app)
    await request.app.state.scheduler.daily_analysis_job()
    return {"status": "triggered", "message": "Daily analysis job executed."}


@router.get("/reconcile/{tenant_id}")
@auth_limit # Item 11: Consistent rate limiting
async def reconcile_tenant_costs(
    request: Request,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(validate_admin_key)
):
    """
    Diagnostic tool to compare Explorer vs CUR data for a tenant.
    Used for investigating billing discrepancies.
    """

    from app.modules.reporting.domain.reconciliation import CostReconciliationService
    service = CostReconciliationService(db)
    
    result = await service.compare_explorer_vs_cur(tenant_id, start_date, end_date)
    return result
