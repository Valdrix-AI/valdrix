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
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.db.session import get_db
from app.core.auth import CurrentUser, requires_role
from app.models.llm import LLMUsage, LLMBudget
from app.models.background_job import BackgroundJob, JobType, JobStatus

logger = structlog.get_logger()
router = APIRouter(prefix="/usage", tags=["Usage Metering"])


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
    cost_explorer_calls_today: int
    zombie_scans_today: int
    regions_scanned: int
    last_scan_at: str | None


class FeatureUsageMetrics(BaseModel):
    """Feature adoption metrics."""
    greenops_enabled: bool
    activeops_enabled: bool
    webhooks_configured: int
    total_remediations: int


class UsageResponse(BaseModel):
    """Complete usage metering response."""
    tenant_id: str
    period: str
    llm: LLMUsageMetrics
    aws: AWSMeteringMetrics
    features: FeatureUsageMetrics
    generated_at: str


@router.get("", response_model=UsageResponse)
async def get_usage_metrics(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get current usage metrics for the tenant.
    
    Shows:
    - LLM token consumption vs budget
    - AWS API call counts
    - Feature adoption
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # LLM Usage
    llm_metrics = await _get_llm_usage(db, user.tenant_id, now)
    
    # AWS Metering
    aws_metrics = await _get_aws_metering(db, user.tenant_id, today_start)
    
    # Feature Usage
    feature_metrics = await _get_feature_usage(db, user.tenant_id)
    
    return UsageResponse(
        tenant_id=str(user.tenant_id),
        period="current_month",
        llm=llm_metrics,
        aws=aws_metrics,
        features=feature_metrics,
        generated_at=now.isoformat()
    )


async def _get_llm_usage(
    db: AsyncSession, 
    tenant_id, 
    now: datetime
) -> LLMUsageMetrics:
    """Get LLM usage for the current billing period."""
    
    # Get budget if exists
    budget = await db.scalar(
        select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
    )
    
    # Get usage for current month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_end = (month_start + timedelta(days=32)).replace(day=1)
    
    result = await db.execute(
        select(
            func.coalesce(func.sum(LLMUsage.tokens_used), 0),
            func.count(LLMUsage.id),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0)
        )
        .where(
            LLMUsage.tenant_id == tenant_id,
            LLMUsage.created_at >= month_start,
            LLMUsage.created_at < month_end
        )
    )
    row = result.one()
    tokens_used = int(row[0])
    requests_count = int(row[1])
    cost_usd = float(row[2])
    
    tokens_limit = budget.monthly_token_limit if budget else 100000
    utilization = (tokens_used / tokens_limit * 100) if tokens_limit > 0 else 0
    
    return LLMUsageMetrics(
        tokens_used=tokens_used,
        tokens_limit=tokens_limit,
        requests_count=requests_count,
        estimated_cost_usd=round(cost_usd, 4),
        period_start=month_start.isoformat(),
        period_end=month_end.isoformat(),
        utilization_percent=round(utilization, 1)
    )


async def _get_aws_metering(
    db: AsyncSession, 
    tenant_id, 
    today_start: datetime
) -> AWSMeteringMetrics:
    """Get AWS API usage for today."""
    
    # Count finops analysis jobs today
    cost_explorer_calls = await db.scalar(
        select(func.count(BackgroundJob.id))
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == JobType.FINOPS_ANALYSIS,
            BackgroundJob.created_at >= today_start
        )
    )
    
    # Count zombie scans today
    zombie_scans = await db.scalar(
        select(func.count(BackgroundJob.id))
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == JobType.ZOMBIE_SCAN,
            BackgroundJob.created_at >= today_start
        )
    )
    
    # Last successful scan
    last_scan = await db.scalar(
        select(BackgroundJob.completed_at)
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.status == JobStatus.COMPLETED
        )
        .order_by(BackgroundJob.completed_at.desc())
        .limit(1)
    )
    
    return AWSMeteringMetrics(
        cost_explorer_calls_today=cost_explorer_calls or 0,
        zombie_scans_today=zombie_scans or 0,
        regions_scanned=4,  # Default regions
        last_scan_at=last_scan.isoformat() if last_scan else None
    )


async def _get_feature_usage(db: AsyncSession, tenant_id) -> FeatureUsageMetrics:
    """Get feature adoption metrics."""
    from app.models.notification_settings import NotificationSettings
    from app.models.remediation import RemediationRequest
    from app.models.tenant import Tenant
    
    # Get tenant settings
    tenant = await db.scalar(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    
    # Check notification settings
    notif = await db.scalar(
        select(NotificationSettings).where(NotificationSettings.tenant_id == tenant_id)
    )
    
    # Count remediations
    remediation_count = await db.scalar(
        select(func.count(RemediationRequest.id))
        .where(RemediationRequest.tenant_id == tenant_id)
    )
    
    # Determine features based on tier
    tier = tenant.plan if tenant else "trial"
    is_paid = tier not in ["trial", "starter"]
    
    return FeatureUsageMetrics(
        greenops_enabled=is_paid,
        activeops_enabled=is_paid,
        webhooks_configured=1 if notif and notif.slack_webhook else 0,
        total_remediations=remediation_count or 0
    )
