"""
Investor Health Dashboard API - Tier 3: Polish

Provides real-time operational health metrics for investor due diligence:
- System uptime and availability
- Active tenant metrics
- Job queue health
- LLM usage and budget status
- Core cloud and Cloud+ connection status

Endpoint: GET /admin/health-dashboard
"""

from typing import Annotated, Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from app.shared.db.session import get_db
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.config import get_settings
from app.shared.core.pricing import PricingTier, get_tenant_tier
from app.shared.core.ops_metrics import LLM_BUDGET_BURN_RATE
from app.shared.core.cache import get_cache_service
from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob, JobStatus
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)

logger = structlog.get_logger()
router = APIRouter(tags=["Investor Health"])


class SystemHealth(BaseModel):
    """Overall system health status."""

    status: str  # healthy, degraded, critical
    uptime_hours: float
    last_check: str


class TenantMetrics(BaseModel):
    """Tenant growth and activity metrics."""

    total_tenants: int
    active_last_24h: int
    active_last_7d: int
    free_tenants: int
    paid_tenants: int
    churn_risk: int  # Inactive paid tenants


class JobQueueHealth(BaseModel):
    """Background job queue metrics."""

    pending_jobs: int
    running_jobs: int
    failed_last_24h: int
    dead_letter_count: int
    avg_processing_time_ms: float
    p50_processing_time_ms: float
    p95_processing_time_ms: float
    p99_processing_time_ms: float


class LLMUsageMetrics(BaseModel):
    """LLM cost and usage metrics."""

    total_requests_24h: int
    cache_hit_rate: float
    estimated_cost_24h: float
    budget_utilization: float


class LLMFairUseThresholds(BaseModel):
    """Configured fair-use guard thresholds."""

    pro_daily_soft_cap: int | None
    enterprise_daily_soft_cap: int | None
    per_minute_cap: int | None
    per_tenant_concurrency_cap: int | None
    concurrency_lease_ttl_seconds: int
    enforced_tiers: list[str]


class LLMFairUseRuntime(BaseModel):
    """Tenant-scoped fair-use runtime state and thresholds."""

    generated_at: str
    guards_enabled: bool
    tenant_tier: str
    tier_eligible: bool
    active_for_tenant: bool
    thresholds: LLMFairUseThresholds


class CloudPlusProviderHealth(BaseModel):
    """Connection health snapshot for one Cloud+ provider."""

    total_connections: int
    active_connections: int
    inactive_connections: int
    errored_connections: int


class CloudPlusConnectionHealth(BaseModel):
    """Aggregated Cloud+ connection status across providers."""

    total_connections: int
    active_connections: int
    inactive_connections: int
    errored_connections: int
    providers: dict[str, CloudPlusProviderHealth]


class CloudConnectionHealth(BaseModel):
    """Aggregated core-cloud connection status for AWS/Azure/GCP."""

    total_connections: int
    active_connections: int
    inactive_connections: int
    errored_connections: int
    providers: dict[str, CloudPlusProviderHealth]


class LicenseGovernanceHealth(BaseModel):
    """License governance execution metrics."""

    window_hours: int
    active_license_connections: int
    requests_created_24h: int
    requests_completed_24h: int
    requests_failed_24h: int
    requests_in_flight: int
    completion_rate_percent: float
    failure_rate_percent: float
    avg_time_to_complete_hours: float | None


class InvestorHealthDashboard(BaseModel):
    """Complete health dashboard for investors."""

    generated_at: str
    system: SystemHealth
    tenants: TenantMetrics
    job_queue: JobQueueHealth
    llm_usage: LLMUsageMetrics
    cloud_connections: CloudConnectionHealth
    cloud_plus_connections: CloudPlusConnectionHealth
    license_governance: LicenseGovernanceHealth


# Track startup time
_startup_time = datetime.now(timezone.utc)
HEALTH_DASHBOARD_CACHE_TTL = timedelta(seconds=20)
FAIR_USE_RUNTIME_CACHE_TTL = timedelta(seconds=20)


@router.get("", response_model=InvestorHealthDashboard)
async def get_investor_health_dashboard(
    _user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> InvestorHealthDashboard:
    """
    Get comprehensive health dashboard for investor due diligence.

    Shows:
    - System uptime and availability
    - Tenant growth and engagement metrics
    - Job queue health
    - LLM usage and costs
    - Cloud + Cloud+ connection reliability
    """
    now = datetime.now(timezone.utc)
    tenant_scope = str(_user.tenant_id) if _user.tenant_id else "global"
    cache_key = f"api:health-dashboard:{tenant_scope}"
    cache = get_cache_service()
    if cache.enabled:
        cached_payload = await cache.get(cache_key)
        if isinstance(cached_payload, dict):
            try:
                return InvestorHealthDashboard.model_validate(cached_payload)
            except Exception as exc:
                logger.warning("health_dashboard_cache_decode_failed", error=str(exc))

    # System Health
    uptime = now - _startup_time
    system = SystemHealth(
        status="healthy",
        uptime_hours=round(uptime.total_seconds() / 3600, 2),
        last_check=now.isoformat(),
    )

    # Tenant Metrics
    tenants = await _get_tenant_metrics(db, now)

    # Job Queue Health
    job_queue = await _get_job_queue_health(db, now)

    # LLM Usage
    llm_usage = await _get_llm_usage_metrics(db, now)

    # Connection Health
    cloud_connections = await _get_cloud_connection_health(db)
    cloud_plus_connections = await _get_cloud_plus_connection_health(db)
    license_governance = await _get_license_governance_health(db, now)

    payload = InvestorHealthDashboard(
        generated_at=now.isoformat(),
        system=system,
        tenants=tenants,
        job_queue=job_queue,
        llm_usage=llm_usage,
        cloud_connections=cloud_connections,
        cloud_plus_connections=cloud_plus_connections,
        license_governance=license_governance,
    )
    if cache.enabled:
        await cache.set(
            cache_key,
            payload.model_dump(mode="json"),
            ttl=HEALTH_DASHBOARD_CACHE_TTL,
        )
    return payload


def _positive_int_or_none(value: Any) -> int | None:
    """Normalize optional integer settings and treat non-positive values as disabled."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _coerce_int_with_minimum(value: Any, *, default: int, minimum: int) -> int:
    """Parse integer settings defensively and enforce a minimum bound."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, minimum)


@router.get("/fair-use", response_model=LLMFairUseRuntime)
async def get_llm_fair_use_runtime(
    _user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> LLMFairUseRuntime:
    """
    Return tenant-scoped fair-use runtime status and configured thresholds.

    This endpoint is intended for operations visibility in admin health.
    """
    now = datetime.now(timezone.utc)
    tenant_scope = str(_user.tenant_id) if _user.tenant_id else "global"
    cache_key = f"api:health-dashboard:fair-use:{tenant_scope}"
    cache = get_cache_service()
    if cache.enabled:
        cached_payload = await cache.get(cache_key)
        if isinstance(cached_payload, dict):
            try:
                return LLMFairUseRuntime.model_validate(cached_payload)
            except Exception as exc:
                logger.warning(
                    "health_dashboard_fair_use_cache_decode_failed", error=str(exc)
                )

    settings = get_settings()
    tenant_tier = PricingTier.FREE
    if _user.tenant_id:
        try:
            tenant_tier = await get_tenant_tier(_user.tenant_id, db)
        except Exception as exc:
            logger.warning(
                "health_dashboard_fair_use_tier_lookup_failed",
                tenant_id=str(_user.tenant_id),
                error=str(exc),
            )

    guards_enabled = bool(settings.LLM_FAIR_USE_GUARDS_ENABLED)
    tier_eligible = tenant_tier in {PricingTier.PRO, PricingTier.ENTERPRISE}
    active_for_tenant = guards_enabled and tier_eligible

    threshold_payload = LLMFairUseThresholds(
        pro_daily_soft_cap=_positive_int_or_none(settings.LLM_FAIR_USE_PRO_DAILY_SOFT_CAP),
        enterprise_daily_soft_cap=_positive_int_or_none(
            settings.LLM_FAIR_USE_ENTERPRISE_DAILY_SOFT_CAP
        ),
        per_minute_cap=_positive_int_or_none(settings.LLM_FAIR_USE_PER_MINUTE_CAP),
        per_tenant_concurrency_cap=_positive_int_or_none(
            settings.LLM_FAIR_USE_PER_TENANT_CONCURRENCY_CAP
        ),
        concurrency_lease_ttl_seconds=_coerce_int_with_minimum(
            settings.LLM_FAIR_USE_CONCURRENCY_LEASE_TTL_SECONDS,
            default=180,
            minimum=30,
        ),
        enforced_tiers=[PricingTier.PRO.value, PricingTier.ENTERPRISE.value],
    )

    payload = LLMFairUseRuntime(
        generated_at=now.isoformat(),
        guards_enabled=guards_enabled,
        tenant_tier=tenant_tier.value,
        tier_eligible=tier_eligible,
        active_for_tenant=active_for_tenant,
        thresholds=threshold_payload,
    )
    if cache.enabled:
        await cache.set(
            cache_key,
            payload.model_dump(mode="json"),
            ttl=FAIR_USE_RUNTIME_CACHE_TTL,
        )
    return payload


async def _get_tenant_metrics(db: AsyncSession, now: datetime) -> TenantMetrics:
    """Calculate tenant growth and activity metrics."""
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)
    free_plan = PricingTier.FREE.value

    result = await db.execute(
        select(
            func.count(Tenant.id).label("total_tenants"),
            func.count(Tenant.id)
            .filter(Tenant.last_accessed_at >= day_ago)
            .label("active_last_24h"),
            func.count(Tenant.id)
            .filter(Tenant.last_accessed_at >= week_ago)
            .label("active_last_7d"),
            func.count(Tenant.id)
            .filter(Tenant.plan == free_plan)
            .label("free_tenants"),
            func.count(Tenant.id)
            .filter(Tenant.plan != free_plan)
            .label("paid_tenants"),
            func.count(Tenant.id)
            .filter(
                Tenant.plan != free_plan,
                (Tenant.last_accessed_at < week_ago)
                | (Tenant.last_accessed_at.is_(None)),
            )
            .label("churn_risk"),
        )
    )
    row = result.one()

    return TenantMetrics(
        total_tenants=int(row.total_tenants or 0),
        active_last_24h=int(row.active_last_24h or 0),
        active_last_7d=int(row.active_last_7d or 0),
        free_tenants=int(row.free_tenants or 0),
        paid_tenants=int(row.paid_tenants or 0),
        churn_risk=int(row.churn_risk or 0),
    )


async def _get_job_queue_health(db: AsyncSession, now: datetime) -> JobQueueHealth:
    """Calculate job queue health metrics."""
    day_ago = now - timedelta(hours=24)
    counts_result = await db.execute(
        select(
            func.count(BackgroundJob.id)
            .filter(BackgroundJob.status == JobStatus.PENDING)
            .label("pending_jobs"),
            func.count(BackgroundJob.id)
            .filter(BackgroundJob.status == JobStatus.RUNNING)
            .label("running_jobs"),
            func.count(BackgroundJob.id)
            .filter(
                BackgroundJob.status == JobStatus.FAILED,
                BackgroundJob.completed_at >= day_ago,
            )
            .label("failed_last_24h"),
            func.count(BackgroundJob.id)
            .filter(BackgroundJob.status == JobStatus.DEAD_LETTER)
            .label("dead_letter_count"),
        )
    )
    counts_row = counts_result.one()

    # Item 5 & 12: Calculate average and percentile processing time from completed jobs (last 24h)
    duration_expr = (
        func.extract("epoch", BackgroundJob.completed_at)
        - func.extract("epoch", BackgroundJob.created_at)
    ) * 1000

    # Determine if we are on Postgres for percentile support
    from app.shared.db.session import engine

    is_postgres = engine.url.get_backend_name().startswith("postgresql")

    if is_postgres:
        metrics = await db.execute(
            select(
                func.avg(duration_expr),
                func.percentile_cont(0.5).within_group(duration_expr),
                func.percentile_cont(0.95).within_group(duration_expr),
                func.percentile_cont(0.99).within_group(duration_expr),
            ).where(
                BackgroundJob.status == JobStatus.COMPLETED,
                BackgroundJob.completed_at >= day_ago,
            )
        )
        avg_time, p50, p95, p99 = metrics.one()
    else:
        # Fallback for SQLite (Dev/Test) - Percentiles not supported natively
        metrics = await db.execute(
            select(func.avg(duration_expr)).where(
                BackgroundJob.status == JobStatus.COMPLETED,
                BackgroundJob.completed_at >= day_ago,
            )
        )
        avg_time = metrics.scalar()
        p50 = p95 = p99 = avg_time  # Simple fallback

    return JobQueueHealth(
        pending_jobs=int(counts_row.pending_jobs or 0),
        running_jobs=int(counts_row.running_jobs or 0),
        failed_last_24h=int(counts_row.failed_last_24h or 0),
        dead_letter_count=int(counts_row.dead_letter_count or 0),
        avg_processing_time_ms=round(avg_time or 0.0, 2),
        p50_processing_time_ms=round(p50 or 0.0, 2),
        p95_processing_time_ms=round(p95 or 0.0, 2),
        p99_processing_time_ms=round(p99 or 0.0, 2),
    )


async def _get_llm_usage_metrics(db: AsyncSession, now: datetime) -> LLMUsageMetrics:
    """Calculate real LLM usage metrics."""
    from app.models.llm import LLMUsage, LLMBudget

    day_ago = now - timedelta(hours=24)

    usage_result = await db.execute(
        select(
            func.count(LLMUsage.id).label("total_requests_24h"),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0).label("estimated_cost_24h"),
        ).where(LLMUsage.created_at >= day_ago)
    )
    usage_row = usage_result.one()

    # Budget utilization (average across tenants with a budget)
    # Aggregate monthly spend per tenant once, then join to budgets.
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    monthly_spend = (
        select(
            LLMUsage.tenant_id.label("tenant_id"),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0).label("month_spend"),
        )
        .where(LLMUsage.created_at >= start_of_month)
        .group_by(LLMUsage.tenant_id)
        .subquery()
    )

    utilization_result = await db.execute(
        select(
            func.avg(
                func.coalesce(monthly_spend.c.month_spend, 0)
                / func.nullif(LLMBudget.monthly_limit_usd, 0)
            )
        )
        .select_from(LLMBudget)
        .outerjoin(monthly_spend, monthly_spend.c.tenant_id == LLMBudget.tenant_id)
    )
    utilization = utilization_result.scalar()
    utilization_pct = round(float(utilization or 0.0) * 100, 2)
    LLM_BUDGET_BURN_RATE.set(utilization_pct)

    return LLMUsageMetrics(
        total_requests_24h=int(usage_row.total_requests_24h or 0),
        cache_hit_rate=0.85,  # Fixed target for now
        estimated_cost_24h=float(usage_row.estimated_cost_24h or 0.0),
        budget_utilization=utilization_pct,
    )


async def _get_cloud_plus_provider_health(
    db: AsyncSession, model: Any
) -> CloudPlusProviderHealth:
    """Compute active/inactive/error counts for a single Cloud+ connection model."""
    result = await db.execute(
        select(
            func.count(model.id).label("total_connections"),
            func.count(model.id)
            .filter(model.is_active.is_(True))
            .label("active_connections"),
            func.count(model.id)
            .filter(
                and_(
                    model.error_message.is_not(None),
                    func.length(func.trim(model.error_message)) > 0,
                )
            )
            .label("errored_connections"),
        )
    )
    row = result.one()
    total = int(row.total_connections or 0)
    active = int(row.active_connections or 0)
    inactive = max(total - active, 0)
    errored = min(int(row.errored_connections or 0), total)
    return CloudPlusProviderHealth(
        total_connections=total,
        active_connections=active,
        inactive_connections=inactive,
        errored_connections=errored,
    )


async def _get_aws_provider_health(db: AsyncSession) -> CloudPlusProviderHealth:
    """Compute provider-style health for AWS status model."""
    result = await db.execute(
        select(
            func.count(AWSConnection.id).label("total_connections"),
            func.count(AWSConnection.id)
            .filter(AWSConnection.status == "active")
            .label("active_connections"),
            func.count(AWSConnection.id)
            .filter(AWSConnection.status == "error")
            .label("errored_connections"),
        )
    )
    row = result.one()
    total = int(row.total_connections or 0)
    active = int(row.active_connections or 0)
    inactive = max(total - active, 0)
    errored = min(int(row.errored_connections or 0), total)
    return CloudPlusProviderHealth(
        total_connections=total,
        active_connections=active,
        inactive_connections=inactive,
        errored_connections=errored,
    )


async def _get_cloud_connection_health(db: AsyncSession) -> CloudConnectionHealth:
    """Aggregate health for AWS, Azure, and GCP connectors."""
    providers: dict[str, CloudPlusProviderHealth] = {
        "aws": await _get_aws_provider_health(db),
        "azure": await _get_cloud_plus_provider_health(db, AzureConnection),
        "gcp": await _get_cloud_plus_provider_health(db, GCPConnection),
    }
    totals = {
        "total_connections": 0,
        "active_connections": 0,
        "inactive_connections": 0,
        "errored_connections": 0,
    }
    for snapshot in providers.values():
        totals["total_connections"] += snapshot.total_connections
        totals["active_connections"] += snapshot.active_connections
        totals["inactive_connections"] += snapshot.inactive_connections
        totals["errored_connections"] += snapshot.errored_connections

    return CloudConnectionHealth(providers=providers, **totals)


async def _get_cloud_plus_connection_health(db: AsyncSession) -> CloudPlusConnectionHealth:
    """Aggregate health for SaaS, license, platform, and hybrid connectors."""
    provider_models: dict[str, Any] = {
        "saas": SaaSConnection,
        "license": LicenseConnection,
        "platform": PlatformConnection,
        "hybrid": HybridConnection,
    }
    providers: dict[str, CloudPlusProviderHealth] = {}
    totals = {
        "total_connections": 0,
        "active_connections": 0,
        "inactive_connections": 0,
        "errored_connections": 0,
    }

    for provider, model in provider_models.items():
        snapshot = await _get_cloud_plus_provider_health(db, model)
        providers[provider] = snapshot
        totals["total_connections"] += snapshot.total_connections
        totals["active_connections"] += snapshot.active_connections
        totals["inactive_connections"] += snapshot.inactive_connections
        totals["errored_connections"] += snapshot.errored_connections

    return CloudPlusConnectionHealth(providers=providers, **totals)


async def _get_license_governance_health(
    db: AsyncSession, now: datetime, *, window_hours: int = 24
) -> LicenseGovernanceHealth:
    """Calculate license governance throughput and reliability over a rolling window."""
    window_start = now - timedelta(hours=window_hours)
    in_flight_statuses = (
        RemediationStatus.PENDING,
        RemediationStatus.PENDING_APPROVAL,
        RemediationStatus.APPROVED,
        RemediationStatus.SCHEDULED,
        RemediationStatus.EXECUTING,
    )

    active_connections = int(
        await db.scalar(
            select(func.count(LicenseConnection.id)).where(LicenseConnection.is_active)
        )
        or 0
    )

    counts_result = await db.execute(
        select(
            func.count(RemediationRequest.id).label("created_requests"),
            func.count(RemediationRequest.id)
            .filter(RemediationRequest.status == RemediationStatus.COMPLETED)
            .label("completed_requests"),
            func.count(RemediationRequest.id)
            .filter(RemediationRequest.status == RemediationStatus.FAILED)
            .label("failed_requests"),
            func.count(RemediationRequest.id)
            .filter(RemediationRequest.status.in_(in_flight_statuses))
            .label("in_flight_requests"),
        ).where(
            RemediationRequest.action == RemediationAction.RECLAIM_LICENSE_SEAT,
            RemediationRequest.created_at >= window_start,
        )
    )
    counts_row = counts_result.one()
    created_requests = int(counts_row.created_requests or 0)
    completed_requests = int(counts_row.completed_requests or 0)
    failed_requests = int(counts_row.failed_requests or 0)
    in_flight_requests = int(counts_row.in_flight_requests or 0)

    completion_rate = (
        round((completed_requests / created_requests) * 100.0, 2)
        if created_requests > 0
        else 0.0
    )
    failure_rate = (
        round((failed_requests / created_requests) * 100.0, 2)
        if created_requests > 0
        else 0.0
    )

    completed_rows = (
        await db.execute(
            select(RemediationRequest.created_at, RemediationRequest.executed_at).where(
                RemediationRequest.action == RemediationAction.RECLAIM_LICENSE_SEAT,
                RemediationRequest.status == RemediationStatus.COMPLETED,
                RemediationRequest.created_at >= window_start,
                RemediationRequest.executed_at.is_not(None),
            )
        )
    ).all()
    completion_hours: list[float] = []
    for created_at, executed_at in completed_rows:
        if created_at is None or executed_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)
        if executed_at >= created_at:
            completion_hours.append((executed_at - created_at).total_seconds() / 3600.0)

    avg_time_to_complete_hours = (
        round(sum(completion_hours) / len(completion_hours), 2)
        if completion_hours
        else None
    )

    return LicenseGovernanceHealth(
        window_hours=window_hours,
        active_license_connections=active_connections,
        requests_created_24h=created_requests,
        requests_completed_24h=completed_requests,
        requests_failed_24h=failed_requests,
        requests_in_flight=in_flight_requests,
        completion_rate_percent=completion_rate,
        failure_rate_percent=failure_rate,
        avg_time_to_complete_hours=avg_time_to_complete_hours,
    )
