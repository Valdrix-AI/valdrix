"""
Leaderboards API Endpoints for Valdrix.
Shows team savings rankings ("Who saved the most?").
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.auth import CurrentUser
from app.shared.core.cache import get_cache_service
from app.shared.core.dependencies import requires_feature
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db
from app.models.remediation import RemediationRequest
from app.shared.core.pricing import FeatureFlag

logger = structlog.get_logger()
router = APIRouter(tags=["Leaderboards"])
LEADERBOARD_CACHE_TTL = timedelta(seconds=30)


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return user.tenant_id


# ============================================================
# Pydantic Schemas
# ============================================================


class LeaderboardEntry(BaseModel):
    """A single entry in the leaderboard."""

    rank: int
    user_email: str
    savings_usd: float
    remediation_count: int


class LeaderboardResponse(BaseModel):
    """Leaderboard response with rankings."""

    period: str
    entries: list[LeaderboardEntry]
    total_team_savings: float


# ============================================================
# API Endpoints
# ============================================================


@router.get("", response_model=LeaderboardResponse)
@rate_limit("60/minute")
async def get_leaderboard(
    request: Request,
    period: str = Query("30d", pattern="^(7d|30d|90d|all)$"),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.COST_TRACKING)),
    db: AsyncSession = Depends(get_db),
) -> LeaderboardResponse:
    """
    Get the savings leaderboard for the current tenant.

    Shows who has approved the most cost-saving remediations.
    """
    from app.models.tenant import User
    from app.models.remediation import RemediationStatus

    # Consumed by slowapi decorator for keying; keep explicit for correctness.
    del request

    tenant_id = _require_tenant_id(current_user)
    cache = get_cache_service()
    cache_key = f"api:leaderboards:{tenant_id}:{period}"
    if cache.enabled:
        cached_payload = await cache.get(cache_key)
        if isinstance(cached_payload, dict):
            try:
                return LeaderboardResponse.model_validate(cached_payload)
            except Exception as exc:
                logger.warning("leaderboard_cache_decode_failed", error=str(exc))

    # Calculate date range
    if period == "all":
        start_date = None
    else:
        days = int(period.replace("d", ""))
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query COMPLETED remediations grouped by approver
    # Join with User table to get email instead of UUID
    query = (
        select(
            User.email.label("user_email"),
            func.sum(RemediationRequest.estimated_monthly_savings).label(
                "total_savings"
            ),
            func.count(RemediationRequest.id).label("remediation_count"),
        )
        .join(User, RemediationRequest.reviewed_by_user_id == User.id)
        .where(
            RemediationRequest.tenant_id == tenant_id,
            RemediationRequest.status == RemediationStatus.COMPLETED,
        )
        .group_by(User.email)
        .order_by(func.sum(RemediationRequest.estimated_monthly_savings).desc())
        .limit(100)
    )

    if start_date:
        query = query.where(RemediationRequest.created_at >= start_date)

    result = await db.execute(query)
    rows = result.fetchall()

    # Build leaderboard entries
    entries = []
    total_savings = 0.0

    for rank, row in enumerate(rows, start=1):
        row_mapping = getattr(row, "_mapping", row)
        user_email = (
            row_mapping.get("user_email")
            if hasattr(row_mapping, "get")
            else getattr(row, "user_email", "")
        )
        row_total_savings = (
            row_mapping.get("total_savings")
            if hasattr(row_mapping, "get")
            else getattr(row, "total_savings", 0)
        )
        remediation_count = (
            row_mapping.get("remediation_count")
            if hasattr(row_mapping, "get")
            else getattr(row, "remediation_count", 0)
        )

        savings = float(row_total_savings or 0)
        total_savings += savings

        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_email=str(user_email or ""),
                savings_usd=savings,
                remediation_count=int(remediation_count or 0),
            )
        )

    period_labels = {
        "7d": "Last 7 Days",
        "30d": "Last 30 Days",
        "90d": "Last 90 Days",
        "all": "All Time",
    }

    payload = LeaderboardResponse(
        period=period_labels.get(period, "Last 30 Days"),
        entries=entries,
        total_team_savings=total_savings,
    )
    if cache.enabled:
        await cache.set(
            cache_key,
            payload.model_dump(mode="json"),
            ttl=LEADERBOARD_CACHE_TTL,
        )
    return payload
