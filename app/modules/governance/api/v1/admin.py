from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Depends, Query
from app.shared.core.config import get_settings
from app.shared.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, case, select
import secrets
import structlog
from uuid import UUID
from app.shared.core.rate_limit import auth_limit
from app.shared.core.proxy_headers import resolve_client_ip
from pydantic import BaseModel, Field

from app.models.landing_telemetry_rollup import LandingTelemetryDailyRollup
from app.shared.core.auth import CurrentUser, requires_role

router = APIRouter(tags=["Admin Utilities"])
logger = structlog.get_logger()


async def validate_admin_key(
    request: Request, x_admin_key: str = Header(..., alias="X-Admin-Key")
) -> bool:
    """Dependency to validate the admin API key with production hardening."""
    settings = get_settings()

    if not settings.ADMIN_API_KEY:
        logger.error("admin_key_not_configured")
        raise HTTPException(
            status_code=503, detail="Admin endpoint not configured. Set ADMIN_API_KEY."
        )

    # Item 11: Prevent weak keys in production
    if settings.ENVIRONMENT == "production" and len(settings.ADMIN_API_KEY) < 32:
        logger.critical("admin_key_too_weak_for_production")
        raise HTTPException(
            status_code=500,
            detail="ADMIN_API_KEY must be at least 32 characters in production.",
        )

    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        # Item 11: Audit failed admin access attempts
        from app.shared.core.logging import audit_log

        client_host = resolve_client_ip(request, settings_obj=settings)
        audit_log(
            "admin_auth_failed",
            "admin_portal",
            str(getattr(request.state, "tenant_id", "unknown")),
            {
                "path": request.url.path,
                "client_ip": client_host,
            },
        )

        logger.warning("admin_auth_failed", client_ip=client_host)
        raise HTTPException(status_code=403, detail="Forbidden")

    return True


@router.post("/trigger-analysis")
@auth_limit  # Item 11: Rate limit admin key checks
async def trigger_analysis(
    request: Request, _: bool = Depends(validate_admin_key)
) -> dict[str, str]:
    """Manually trigger a scheduled analysis job."""

    logger.info("manual_trigger_requested")
    # Access scheduler from app state (passed via request.app)
    await request.app.state.scheduler.daily_analysis_job()
    return {"status": "triggered", "message": "Daily analysis job executed."}


@router.get("/reconcile/{tenant_id}")
@auth_limit  # Item 11: Consistent rate limiting
async def reconcile_tenant_costs(
    request: Request,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    provider: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(validate_admin_key),
) -> dict[str, Any]:
    """
    Diagnostic tool to compare Explorer vs CUR data for a tenant.
    Used for investigating billing discrepancies.
    """

    from app.modules.reporting.domain.reconciliation import CostReconciliationService

    service = CostReconciliationService(db)

    try:
        result = await service.compare_explorer_vs_cur(
            tenant_id,
            start_date,
            end_date,
            provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


class LandingCampaignMetricsRow(BaseModel):
    utm_source: str = Field(default="direct")
    utm_medium: str = Field(default="direct")
    utm_campaign: str = Field(default="direct")
    total_events: int
    cta_events: int
    signup_intent_events: int
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class LandingCampaignMetricsResponse(BaseModel):
    window_start: date
    window_end: date
    days: int
    total_events: int
    items: list[LandingCampaignMetricsRow]


@router.get("/landing/campaigns", response_model=LandingCampaignMetricsResponse)
@auth_limit
async def get_landing_campaign_metrics(
    request: Request,
    days: int = Query(default=30, ge=1, le=120),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(requires_role("admin")),
) -> LandingCampaignMetricsResponse:
    del request
    del user

    window_end = datetime.now(timezone.utc).date()
    window_start = window_end - timedelta(days=days - 1)

    total_events_expr = func.sum(LandingTelemetryDailyRollup.event_count)
    cta_events_expr = func.sum(
        case(
            (LandingTelemetryDailyRollup.funnel_stage == "cta", LandingTelemetryDailyRollup.event_count),
            else_=0,
        )
    )
    signup_intent_expr = func.sum(
        case(
            (
                LandingTelemetryDailyRollup.funnel_stage == "signup_intent",
                LandingTelemetryDailyRollup.event_count,
            ),
            else_=0,
        )
    )

    stmt = (
        select(
            LandingTelemetryDailyRollup.utm_source,
            LandingTelemetryDailyRollup.utm_medium,
            LandingTelemetryDailyRollup.utm_campaign,
            total_events_expr.label("total_events"),
            cta_events_expr.label("cta_events"),
            signup_intent_expr.label("signup_intent_events"),
            func.min(LandingTelemetryDailyRollup.first_seen_at).label("first_seen_at"),
            func.max(LandingTelemetryDailyRollup.last_seen_at).label("last_seen_at"),
        )
        .where(LandingTelemetryDailyRollup.event_date >= window_start)
        .where(LandingTelemetryDailyRollup.event_date <= window_end)
        .group_by(
            LandingTelemetryDailyRollup.utm_source,
            LandingTelemetryDailyRollup.utm_medium,
            LandingTelemetryDailyRollup.utm_campaign,
        )
        .order_by(total_events_expr.desc())
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()
    items = [
        LandingCampaignMetricsRow(
            utm_source=(row.utm_source or "direct"),
            utm_medium=(row.utm_medium or "direct"),
            utm_campaign=(row.utm_campaign or "direct"),
            total_events=int(row.total_events or 0),
            cta_events=int(row.cta_events or 0),
            signup_intent_events=int(row.signup_intent_events or 0),
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]

    return LandingCampaignMetricsResponse(
        window_start=window_start,
        window_end=window_end,
        days=days,
        total_events=sum(item.total_events for item in items),
        items=items,
    )
