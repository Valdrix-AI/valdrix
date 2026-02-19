"""
Usage Metering API - Tier 3: Polish

Displays real-time usage metrics for tenants:
- AWS API calls consumed
- LLM tokens used
- Storage consumption
- Feature usage

Endpoint: GET /usage
"""

from typing import Annotated
from uuid import UUID
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.shared.db.session import get_db
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.cache import get_cache_service
from app.models.llm import LLMUsage, LLMBudget
from app.models.background_job import BackgroundJob, JobType, JobStatus

logger = structlog.get_logger()
router = APIRouter(tags=["Usage Metering"])
USAGE_METRICS_CACHE_TTL = timedelta(seconds=20)


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise ValueError("tenant_id is required for usage metrics")
    return user.tenant_id


class LLMUsageMetrics(BaseModel):
    """LLM usage for the current period."""

    tokens_used: int
    tokens_limit: int
    requests_count: int
    estimated_cost_usd: float
    period_start: str
    period_end: str
    utilization_percent: float


class AWSMeteringMetrics(BaseModel):
    """AWS API usage metrics."""

    cost_analysis_calls_today: int
    zombie_scans_today: int
    regions_scanned: int
    last_scan_at: str | None


class FeatureUsageMetrics(BaseModel):
    """Feature adoption metrics."""

    greenops_enabled: bool
    activeops_enabled: bool
    webhooks_configured: int
    total_remediations: int


class LLMUsageRecord(BaseModel):
    """Individual LLM usage record."""

    id: UUID
    created_at: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    request_type: str | None = None


class UsageResponse(BaseModel):
    """Complete usage metering response."""

    tenant_id: UUID
    period: str
    llm: LLMUsageMetrics
    usage: list[LLMUsageRecord]  # Added for dashboard
    aws: AWSMeteringMetrics
    features: FeatureUsageMetrics
    generated_at: str


@router.get("", response_model=UsageResponse)
async def get_usage_metrics(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """
    Get current usage metrics for the tenant.

    Shows:
    - LLM token consumption vs budget
    - AWS API call counts
    - Feature adoption
    - Recent LLM usage (last 20 records)
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tenant_id = _require_tenant_id(user)
    cache = get_cache_service()
    cache_key = f"api:usage:{tenant_id}"
    if cache.enabled:
        cached_payload = await cache.get(cache_key)
        if isinstance(cached_payload, dict):
            try:
                return UsageResponse.model_validate(cached_payload)
            except Exception as exc:
                logger.warning("usage_metrics_cache_decode_failed", error=str(exc))

    # LLM Usage Aggregates
    llm_metrics = await _get_llm_usage(db, tenant_id, now)

    # Recent LLM Usage Records
    recent_usage = await _get_recent_llm_activity(db, tenant_id)

    # AWS Metering
    aws_metrics = await _get_aws_metering(db, tenant_id, today_start)

    # Feature Usage
    feature_metrics = await _get_feature_usage(db, tenant_id)

    payload = UsageResponse(
        tenant_id=tenant_id,
        period="current_month",
        llm=llm_metrics,
        usage=recent_usage,
        aws=aws_metrics,
        features=feature_metrics,
        generated_at=now.isoformat(),
    )
    if cache.enabled:
        await cache.set(
            cache_key,
            payload.model_dump(mode="json"),
            ttl=USAGE_METRICS_CACHE_TTL,
        )
    return payload


async def _get_recent_llm_activity(
    db: AsyncSession, tenant_id: UUID
) -> list[LLMUsageRecord]:
    """Get the 20 most recent LLM usage records."""
    result = await db.execute(
        select(LLMUsage)
        .where(LLMUsage.tenant_id == tenant_id)
        .order_by(LLMUsage.created_at.desc())
        .limit(20)
    )
    records = result.scalars().all()

    return [
        LLMUsageRecord(
            id=rec.id,
            created_at=rec.created_at.isoformat(),
            model=rec.model,
            input_tokens=rec.input_tokens,
            output_tokens=rec.output_tokens,
            total_tokens=rec.total_tokens,
            cost_usd=float(rec.cost_usd),
            request_type=rec.request_type,
        )
        for rec in records
    ]


async def _get_llm_usage(
    db: AsyncSession, tenant_id: UUID, now: datetime
) -> LLMUsageMetrics:
    """Get LLM usage for the current billing period."""

    # Get usage for current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)

    budget_limit_subquery = (
        select(LLMBudget.monthly_limit_usd)
        .where(LLMBudget.tenant_id == tenant_id)
        .limit(1)
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            func.coalesce(func.sum(LLMUsage.total_tokens), 0).label("tokens_used"),
            func.count(LLMUsage.id).label("requests_count"),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0).label("cost_usd"),
            budget_limit_subquery.label("budget_limit_usd"),
        ).where(
            LLMUsage.tenant_id == tenant_id,
            LLMUsage.created_at >= month_start,
            LLMUsage.created_at < month_end,
        )
    )
    row = result.one()
    tokens_used = int(row.tokens_used or 0)
    requests_count = int(row.requests_count or 0)
    cost_usd = float(row.cost_usd or 0)
    budget_limit = row.budget_limit_usd

    # If no token limit set, we use an approximate one based on USD limit ($1 = ~100k tokens at avg price)
    tokens_limit = (
        int(float(budget_limit) * 100000) if budget_limit is not None else 100000
    )
    utilization = (tokens_used / tokens_limit * 100) if tokens_limit > 0 else 0

    return LLMUsageMetrics(
        tokens_used=tokens_used,
        tokens_limit=tokens_limit,
        requests_count=requests_count,
        estimated_cost_usd=round(cost_usd, 4),
        period_start=month_start.isoformat(),
        period_end=month_end.isoformat(),
        utilization_percent=round(utilization, 1),
    )


async def _get_aws_metering(
    db: AsyncSession, tenant_id: UUID, today_start: datetime
) -> AWSMeteringMetrics:
    """Get AWS API usage for today."""
    result = await db.execute(
        select(
            func.count(BackgroundJob.id)
            .filter(
                BackgroundJob.job_type == JobType.FINOPS_ANALYSIS,
                BackgroundJob.created_at >= today_start,
            )
            .label("cost_analysis_calls"),
            func.count(BackgroundJob.id)
            .filter(
                BackgroundJob.job_type == JobType.ZOMBIE_SCAN,
                BackgroundJob.created_at >= today_start,
            )
            .label("zombie_scans"),
            func.max(BackgroundJob.completed_at)
            .filter(BackgroundJob.status == JobStatus.COMPLETED)
            .label("last_scan"),
        ).where(BackgroundJob.tenant_id == tenant_id)
    )
    row = result.one()

    return AWSMeteringMetrics(
        cost_analysis_calls_today=int(row.cost_analysis_calls or 0),
        zombie_scans_today=int(row.zombie_scans or 0),
        regions_scanned=4,  # Default regions
        last_scan_at=row.last_scan.isoformat() if row.last_scan else None,
    )


async def _get_feature_usage(db: AsyncSession, tenant_id: UUID) -> FeatureUsageMetrics:
    """Get feature adoption metrics."""
    from app.models.notification_settings import NotificationSettings
    from app.models.remediation import RemediationRequest
    from app.models.tenant import Tenant

    tenant_plan_subquery = (
        select(Tenant.plan).where(Tenant.id == tenant_id).limit(1).scalar_subquery()
    )
    slack_enabled_subquery = (
        select(func.max(cast(NotificationSettings.slack_enabled, Integer)))
        .where(NotificationSettings.tenant_id == tenant_id)
        .scalar_subquery()
    )
    remediation_count_subquery = (
        select(func.count(RemediationRequest.id))
        .where(RemediationRequest.tenant_id == tenant_id)
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            tenant_plan_subquery.label("tenant_plan"),
            func.coalesce(slack_enabled_subquery, 0).label("slack_enabled"),
            remediation_count_subquery.label("remediation_count"),
        )
    )
    row = result.one()

    # Determine features based on tier
    tier_raw = row.tenant_plan if row.tenant_plan else "free"
    tier = tier_raw.value if hasattr(tier_raw, "value") else str(tier_raw)
    is_paid = tier.lower() not in {"free", "starter"}

    return FeatureUsageMetrics(
        greenops_enabled=is_paid,
        activeops_enabled=is_paid,
        webhooks_configured=1 if int(row.slack_enabled or 0) > 0 else 0,
        total_remediations=int(row.remediation_count or 0),
    )
