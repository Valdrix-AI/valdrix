from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID
from decimal import Decimal
import math
from pydantic import BaseModel, Field
import structlog

from app.shared.db.session import get_db
from app.shared.core.auth import get_current_user, requires_role, CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.notifications import NotificationDispatcher
from app.modules.reporting.domain.aggregator import CostAggregator, LARGE_DATASET_THRESHOLD
from app.modules.reporting.domain.reconciliation import CostReconciliationService
from app.models.cloud import CostRecord, CloudAccount
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.unit_economics_settings import UnitEconomicsSettings
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.factory import LLMFactory
from app.shared.core.pricing import FeatureFlag, PricingTier, is_feature_enabled, normalize_tier
from sqlalchemy import func, select

router = APIRouter(tags=["Costs"])
logger = structlog.get_logger()
SUPPORTED_PROVIDER_FILTERS = {"aws", "azure", "gcp", "saas", "license"}


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return user.tenant_id


def _resolve_user_tier(user: CurrentUser) -> PricingTier:
    return normalize_tier(getattr(user, "tier", PricingTier.FREE_TRIAL))


def _normalize_provider_filter(provider: str | None) -> str | None:
    if provider is None:
        return None
    normalized = provider.strip().lower()
    if not normalized:
        return None
    if normalized not in SUPPORTED_PROVIDER_FILTERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDER_FILTERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'. Use one of: {supported}",
        )
    return normalized


class UnitEconomicsSettingsResponse(BaseModel):
    id: UUID
    default_request_volume: float
    default_workload_volume: float
    default_customer_volume: float
    anomaly_threshold_percent: float


class UnitEconomicsSettingsUpdate(BaseModel):
    default_request_volume: Optional[float] = Field(default=None, gt=0)
    default_workload_volume: Optional[float] = Field(default=None, gt=0)
    default_customer_volume: Optional[float] = Field(default=None, gt=0)
    anomaly_threshold_percent: Optional[float] = Field(default=None, gt=0, le=1000)


class UnitEconomicsMetric(BaseModel):
    metric_key: str
    label: str
    denominator: float
    total_cost: float
    cost_per_unit: float
    baseline_cost_per_unit: float
    delta_percent: float
    is_anomalous: bool


class UnitEconomicsResponse(BaseModel):
    start_date: str
    end_date: str
    total_cost: float
    baseline_total_cost: float
    threshold_percent: float
    anomaly_count: int
    alert_dispatched: bool
    metrics: list[UnitEconomicsMetric]


class IngestionSLAResponse(BaseModel):
    window_hours: int
    target_success_rate_percent: float
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    success_rate_percent: float
    meets_sla: bool
    latest_completed_at: Optional[str]
    avg_duration_seconds: Optional[float]
    p95_duration_seconds: Optional[float]
    records_ingested: int


async def _get_or_create_unit_settings(db: AsyncSession, tenant_id: UUID) -> UnitEconomicsSettings:
    settings = await db.scalar(
        select(UnitEconomicsSettings).where(UnitEconomicsSettings.tenant_id == tenant_id)
    )
    if settings:
        return settings

    settings = UnitEconomicsSettings(tenant_id=tenant_id)
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


def _settings_to_response(settings: UnitEconomicsSettings) -> UnitEconomicsSettingsResponse:
    return UnitEconomicsSettingsResponse(
        id=settings.id,
        default_request_volume=float(settings.default_request_volume),
        default_workload_volume=float(settings.default_workload_volume),
        default_customer_volume=float(settings.default_customer_volume),
        anomaly_threshold_percent=float(settings.anomaly_threshold_percent),
    )


async def _window_total_cost(
    db: AsyncSession,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    provider: Optional[str] = None,
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(CostRecord.cost_usd), 0))
        .where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= start_date,
            CostRecord.recorded_at <= end_date,
        )
    )
    if provider:
        stmt = stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
            CloudAccount.provider == provider.lower()
        )
    result = await db.execute(stmt)
    value = result.scalar_one_or_none()
    if value is None:
        return Decimal("0")
    return Decimal(value)


def _build_unit_metrics(
    total_cost: Decimal,
    baseline_total_cost: Decimal,
    threshold_percent: float,
    request_volume: float,
    workload_volume: float,
    customer_volume: float,
) -> list[UnitEconomicsMetric]:
    defs = [
        ("cost_per_request", "Cost Per Request", request_volume),
        ("cost_per_workload", "Cost Per Workload", workload_volume),
        ("cost_per_customer", "Cost Per Customer", customer_volume),
    ]

    metrics: list[UnitEconomicsMetric] = []
    for key, label, denominator in defs:
        if denominator <= 0:
            continue
        current_cpu = float(total_cost / Decimal(str(denominator)))
        baseline_cpu = float(baseline_total_cost / Decimal(str(denominator)))
        if baseline_cpu > 0:
            delta = ((current_cpu - baseline_cpu) / baseline_cpu) * 100
        else:
            delta = 0.0
        is_anomalous = baseline_cpu > 0 and delta >= threshold_percent
        metrics.append(
            UnitEconomicsMetric(
                metric_key=key,
                label=label,
                denominator=round(denominator, 4),
                total_cost=float(total_cost),
                cost_per_unit=round(current_cpu, 6),
                baseline_cost_per_unit=round(baseline_cpu, 6),
                delta_percent=round(delta, 2),
                is_anomalous=is_anomalous,
            )
        )
    return metrics

@router.get("")
async def get_costs(
    response: Response,
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns aggregated cost metrics for the selected time period.
    Supports filtering by provider (aws, azure, gcp).
    """
    tenant_id = _require_tenant_id(current_user)
    record_count = await CostAggregator.count_records(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )

    if record_count > LARGE_DATASET_THRESHOLD:
        from app.modules.governance.domain.jobs.processor import enqueue_job
        from app.models.background_job import JobType

        job = await enqueue_job(
            db=db,
            tenant_id=tenant_id,
            job_type=JobType.COST_AGGREGATION,
            payload={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "provider": provider,
            },
        )
        response.status_code = 202
        return {
            "status": "accepted",
            "job_id": str(job.id),
            "record_count": record_count,
            "threshold": LARGE_DATASET_THRESHOLD,
        }

    return await CostAggregator.get_dashboard_summary(db, tenant_id, start_date, end_date, provider)

@router.get("/breakdown")
async def get_cost_breakdown(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """Provides a service-level cost breakdown."""
    tenant_id = _require_tenant_id(current_user)
    return await CostAggregator.get_basic_breakdown(
        db, tenant_id, start_date, end_date, provider
    )

@router.get("/attribution/summary")
async def get_cost_attribution_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    bucket: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    """
    Returns cost allocation summary grouped by attribution bucket.
    """
    tenant_id = _require_tenant_id(current_user)
    from app.modules.reporting.domain.attribution_engine import AttributionEngine

    attribution_engine = AttributionEngine(db)
    return await attribution_engine.get_allocation_summary(
        tenant_id=tenant_id,
        start_date=datetime.combine(start_date, time.min, tzinfo=timezone.utc),
        end_date=datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        bucket=bucket,
    )


@router.get("/attribution/coverage")
async def get_cost_attribution_coverage(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    """
    Returns allocation coverage KPI against the 90% target.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    tenant_id = _require_tenant_id(current_user)
    from app.modules.reporting.domain.attribution_engine import AttributionEngine

    attribution_engine = AttributionEngine(db)
    return await attribution_engine.get_allocation_coverage(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        target_percentage=90.0,
    )


@router.get("/canonical/quality")
async def get_canonical_quality(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    notify_on_breach: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Returns canonical mapping quality metrics and optional breach alerting.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    tenant_id = _require_tenant_id(current_user)
    normalized_provider = _normalize_provider_filter(provider)
    quality = await CostAggregator.get_canonical_data_quality(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        provider=normalized_provider,
    )

    if notify_on_breach and quality.get("total_records", 0) > 0 and not quality.get("meets_target", False):
        try:
            await NotificationDispatcher.send_alert(
                title=f"Canonical mapping coverage below target ({quality.get('mapped_percentage', 0)}%)",
                message=(
                    f"Tenant {tenant_id} canonical mapping coverage is "
                    f"{quality.get('mapped_percentage', 0)}% vs target {quality.get('target_percentage', 99.0)}%. "
                    f"Unmapped records: {quality.get('unmapped_records', 0)}."
                ),
                severity="warning",
            )
            quality["alert_triggered"] = True
        except Exception as exc:
            logger.error("canonical_quality_alert_failed", error=str(exc), tenant_id=str(tenant_id))
            quality["alert_triggered"] = False
            quality["alert_error"] = str(exc)
    return quality

@router.get("/forecast")
async def get_cost_forecast(
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generates a cost forecast using the Symbolic Forecasting engine.
    """
    from app.shared.analysis.forecaster import SymbolicForecaster
    
    tenant_id = _require_tenant_id(current_user)
    # Fetch last 30 days for forecasting context
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    summary = await CostAggregator.get_summary(
        db, tenant_id, start_date, end_date
    )
    
    if not summary.records:
        raise HTTPException(status_code=400, detail="Insufficient cost history for forecasting.")
        
    return await SymbolicForecaster.forecast(
        summary.records, 
        days=days,
        db=db,
        tenant_id=tenant_id
    )

@router.post("/analyze")
async def analyze_costs(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.LLM_ANALYSIS)),
) -> Dict[str, Any]:
    """
    Triggers an AI-powered analysis of the cost data.
    Requires Growth tier or higher.
    """
    tenant_id = _require_tenant_id(current_user)
    # 1. Fetch data
    summary = await CostAggregator.get_summary(
        db, tenant_id, start_date, end_date, provider
    )
    
    if not summary.records:
        return {
            "summary": "No cost data available for analysis.",
            "anomalies": [],
            "recommendations": [],
            "estimated_total_savings": 0.0
        }

    # 2. Initialize LLM
    llm = LLMFactory.create()
    analyzer = FinOpsAnalyzer(llm, db)
    
    # 3. Analyze
    result = await analyzer.analyze(
        usage_summary=summary,
        tenant_id=tenant_id,
        db=db,
        provider=provider
    )
    
    return result

@router.post("/ingest")
async def trigger_ingest(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_role("admin")),
) -> Dict[str, str]:
    """
    Manually triggers cost ingestion for active cloud connections.
    """
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(status_code=400, detail="Both start_date and end_date are required for backfill")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    if start_date is not None and end_date is not None:
        user_tier = _resolve_user_tier(current_user)
        if not is_feature_enabled(user_tier, FeatureFlag.INGESTION_BACKFILL):
            raise HTTPException(
                status_code=403,
                detail="Historical backfill requires Growth tier or higher. Please upgrade.",
            )

    tenant_id = _require_tenant_id(current_user)
    from app.modules.governance.domain.jobs.processor import enqueue_job
    from app.models.background_job import JobType

    payload: Dict[str, Any] = {}
    if start_date is not None and end_date is not None:
        payload = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
    
    job = await enqueue_job(
        db=db,
        tenant_id=tenant_id,
        job_type=JobType.COST_INGESTION,
        payload=payload
    )
    response: Dict[str, str] = {"status": "queued", "job_id": str(job.id)}
    if payload:
        response["start_date"] = payload["start_date"]
        response["end_date"] = payload["end_date"]
    return response


@router.get("/ingestion/sla", response_model=IngestionSLAResponse)
async def get_ingestion_sla(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    target_success_rate_percent: float = Query(default=95.0, ge=0, le=100),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.INGESTION_SLA)),
    db: AsyncSession = Depends(get_db),
) -> IngestionSLAResponse:
    """
    Returns SLA monitoring metrics for cost ingestion jobs in a rolling window.
    """
    tenant_id = _require_tenant_id(user)
    window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    result = await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == JobType.COST_INGESTION.value,
            BackgroundJob.created_at >= window_start,
        )
    )
    jobs = list(result.scalars().all())

    total_jobs = len(jobs)
    successful_jobs = sum(1 for job in jobs if job.status == JobStatus.COMPLETED.value)
    failed_jobs = sum(
        1 for job in jobs if job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
    )
    success_rate_percent = round((successful_jobs / total_jobs) * 100, 2) if total_jobs else 0.0
    meets_sla = total_jobs > 0 and success_rate_percent >= target_success_rate_percent

    latest_completed_at_dt: Optional[datetime] = None
    duration_samples: list[float] = []
    records_ingested = 0

    for job in jobs:
        if job.completed_at and (
            latest_completed_at_dt is None or job.completed_at > latest_completed_at_dt
        ):
            latest_completed_at_dt = job.completed_at

        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            if duration >= 0:
                duration_samples.append(duration)

        if job.status == JobStatus.COMPLETED.value and isinstance(job.result, dict):
            ingested_value = job.result.get("ingested")
            if isinstance(ingested_value, (int, float)):
                records_ingested += int(ingested_value)

    avg_duration_seconds = (
        round(sum(duration_samples) / len(duration_samples), 2) if duration_samples else None
    )
    p95_duration_seconds: Optional[float] = None
    if duration_samples:
        sorted_durations = sorted(duration_samples)
        p95_index = max(0, math.ceil(len(sorted_durations) * 0.95) - 1)
        p95_duration_seconds = round(sorted_durations[p95_index], 2)

    return IngestionSLAResponse(
        window_hours=window_hours,
        target_success_rate_percent=round(target_success_rate_percent, 2),
        total_jobs=total_jobs,
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        success_rate_percent=success_rate_percent,
        meets_sla=meets_sla,
        latest_completed_at=latest_completed_at_dt.isoformat() if latest_completed_at_dt else None,
        avg_duration_seconds=avg_duration_seconds,
        p95_duration_seconds=p95_duration_seconds,
        records_ingested=records_ingested,
    )


@router.get("/unit-economics/settings", response_model=UnitEconomicsSettingsResponse)
async def get_unit_economics_settings(
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS)),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsSettingsResponse:
    tenant_id = _require_tenant_id(user)
    settings = await _get_or_create_unit_settings(db, tenant_id)
    return _settings_to_response(settings)


@router.put("/unit-economics/settings", response_model=UnitEconomicsSettingsResponse)
async def update_unit_economics_settings(
    payload: UnitEconomicsSettingsUpdate,
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS, "admin")),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsSettingsResponse:
    tenant_id = _require_tenant_id(user)
    settings = await _get_or_create_unit_settings(db, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings, key, value)
    await db.commit()
    await db.refresh(settings)
    return _settings_to_response(settings)


@router.get("/unit-economics", response_model=UnitEconomicsResponse)
async def get_unit_economics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    request_volume: Optional[float] = Query(default=None, gt=0),
    workload_volume: Optional[float] = Query(default=None, gt=0),
    customer_volume: Optional[float] = Query(default=None, gt=0),
    alert_on_anomaly: bool = Query(default=True),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS)),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsResponse:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = _require_tenant_id(user)
    settings = await _get_or_create_unit_settings(db, tenant_id)

    total_cost = await _window_total_cost(db, tenant_id, start_date, end_date, provider)
    window_days = (end_date - start_date).days + 1
    baseline_end = start_date - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=window_days - 1)
    baseline_total_cost = await _window_total_cost(db, tenant_id, baseline_start, baseline_end, provider)

    req_volume = float(request_volume or settings.default_request_volume)
    wkl_volume = float(workload_volume or settings.default_workload_volume)
    cst_volume = float(customer_volume or settings.default_customer_volume)
    threshold = float(settings.anomaly_threshold_percent)

    metrics = _build_unit_metrics(
        total_cost=total_cost,
        baseline_total_cost=baseline_total_cost,
        threshold_percent=threshold,
        request_volume=req_volume,
        workload_volume=wkl_volume,
        customer_volume=cst_volume,
    )
    anomalies = [metric for metric in metrics if metric.is_anomalous]

    alert_dispatched = False
    if anomalies and alert_on_anomaly:
        try:
            top = anomalies[0]
            await NotificationDispatcher.send_alert(
                title="Unit Economics Anomaly Detected",
                message=(
                    f"Tenant {tenant_id}: {top.label} increased by {top.delta_percent:.2f}% "
                    f"from baseline for {start_date.isoformat()} to {end_date.isoformat()}."
                ),
                severity="warning",
            )
            alert_dispatched = True
        except Exception as exc:
            logger.error("unit_economics_alert_failed", error=str(exc), tenant_id=str(tenant_id))

    return UnitEconomicsResponse(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_cost=float(total_cost),
        baseline_total_cost=float(baseline_total_cost),
        threshold_percent=threshold,
        anomaly_count=len(anomalies),
        alert_dispatched=alert_dispatched,
        metrics=metrics,
    )


@router.get("/reconciliation/close-package", response_model=None)
async def get_reconciliation_close_package(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    enforce_finalized: bool = Query(default=True),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.CLOSE_WORKFLOW)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Generates a deterministic month-end close package.
    Returns JSON by default or CSV when response_format=csv.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = _require_tenant_id(user)
    normalized_provider = _normalize_provider_filter(provider)
    service = CostReconciliationService(db)
    try:
        package = await service.generate_close_package(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            enforce_finalized=enforce_finalized,
            provider=normalized_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if response_format == "csv":
        return Response(content=package["csv"], media_type="text/csv")
    return package


@router.get("/reconciliation/restatements", response_model=None)
async def get_restatement_history(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.RECONCILIATION)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Returns restatement history for a period and supports CSV export.
    """
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = _require_tenant_id(user)
    normalized_provider = _normalize_provider_filter(provider)
    service = CostReconciliationService(db)
    export_csv = response_format == "csv"
    payload = await service.get_restatement_history(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        export_csv=export_csv,
        provider=normalized_provider,
    )

    if export_csv:
        return Response(content=payload["csv"], media_type="text/csv")
    return payload
