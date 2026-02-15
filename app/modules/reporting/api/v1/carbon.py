import asyncio
from datetime import date, datetime, time, timezone, timedelta
from typing import Annotated, Any, Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.carbon_settings import CarbonSettings
from app.models.gcp_connection import GCPConnection
from app.models.carbon_factors import CarbonFactorSet, CarbonFactorUpdateLog
from app.modules.reporting.domain.budget_alerts import CarbonBudgetService
from app.modules.reporting.domain.calculator import CarbonCalculator
from app.modules.reporting.domain.carbon_factors import CarbonFactorService
from app.modules.reporting.domain.carbon_scheduler import CarbonAwareScheduler
from app.modules.reporting.domain.graviton_analyzer import GravitonAnalyzer
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.auth import CurrentUser
from app.shared.core.cache import get_cache_service
from app.shared.core.config import get_settings
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db

router = APIRouter(tags=["GreenOps & Carbon"])
logger = structlog.get_logger()
SUPPORTED_CARBON_PROVIDERS = {"aws", "azure", "gcp"}
CARBON_FOOTPRINT_CACHE_TTL = timedelta(minutes=5)
CARBON_BUDGET_CACHE_TTL = timedelta(minutes=3)
CARBON_GRAVITON_CACHE_TTL = timedelta(minutes=10)
CARBON_INTENSITY_CACHE_TTL = timedelta(minutes=5)
CARBON_SCHEDULE_CACHE_TTL = timedelta(minutes=3)


class CarbonFactorStageRequest(BaseModel):
    payload: Dict[str, Any] = Field(
        ..., description="Full canonical carbon factor payload."
    )
    message: str | None = Field(default=None, description="Optional operator notes.")


class CarbonFactorSetItem(BaseModel):
    id: str
    status: str
    is_active: bool
    factor_source: str
    factor_version: str
    factor_timestamp: str
    methodology_version: str
    factors_checksum_sha256: str
    created_at: str
    activated_at: str | None


class CarbonFactorSetListResponse(BaseModel):
    total: int
    items: list[CarbonFactorSetItem]


class CarbonFactorUpdateLogItem(BaseModel):
    id: str
    recorded_at: str
    action: str
    message: str | None
    old_factor_set_id: str | None
    new_factor_set_id: str | None
    old_checksum_sha256: str | None
    new_checksum_sha256: str | None
    details: Dict[str, Any]


class CarbonFactorUpdateLogListResponse(BaseModel):
    total: int
    items: list[CarbonFactorUpdateLogItem]


def _factor_set_to_item(row: CarbonFactorSet) -> CarbonFactorSetItem:
    return CarbonFactorSetItem(
        id=str(row.id),
        status=str(row.status),
        is_active=bool(row.is_active),
        factor_source=str(row.factor_source),
        factor_version=str(row.factor_version),
        factor_timestamp=row.factor_timestamp.isoformat(),
        methodology_version=str(row.methodology_version),
        factors_checksum_sha256=str(row.factors_checksum_sha256),
        created_at=row.created_at.isoformat(),
        activated_at=row.activated_at.isoformat() if row.activated_at else None,
    )


def _update_log_to_item(row: CarbonFactorUpdateLog) -> CarbonFactorUpdateLogItem:
    return CarbonFactorUpdateLogItem(
        id=str(row.id),
        recorded_at=row.recorded_at.isoformat(),
        action=str(row.action),
        message=row.message,
        old_factor_set_id=str(row.old_factor_set_id) if row.old_factor_set_id else None,
        new_factor_set_id=str(row.new_factor_set_id) if row.new_factor_set_id else None,
        old_checksum_sha256=row.old_checksum_sha256,
        new_checksum_sha256=row.new_checksum_sha256,
        details=row.details if isinstance(row.details, dict) else {},
    )


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")
    return user.tenant_id


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_CARBON_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_CARBON_PROVIDERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'. Use one of: {supported}",
        )
    return normalized


async def _get_provider_connection(
    db: AsyncSession,
    tenant_id: UUID,
    provider: str,
) -> Any | None:
    if provider == "aws":
        result = await db.execute(
            select(AWSConnection).where(AWSConnection.tenant_id == tenant_id).limit(1)
        )
        return result.scalar_one_or_none()
    if provider == "azure":
        result = await db.execute(
            select(AzureConnection)
            .where(
                AzureConnection.tenant_id == tenant_id,
                AzureConnection.is_active.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        (
            select(GCPConnection)
            .where(
                GCPConnection.tenant_id == tenant_id, GCPConnection.is_active.is_(True)
            )
            .limit(1)
        )
    )
    return result.scalar_one_or_none()


async def _fetch_provider_cost_data(
    connection: Any,
    provider: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    adapter = AdapterFactory.get_adapter(connection)

    if provider == "aws" and hasattr(adapter, "get_gross_usage"):
        rows = await adapter.get_gross_usage(start_date, end_date)
        return [{**row, "provider": provider} for row in rows]

    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    rows = await adapter.get_cost_and_usage(start_dt, end_dt, granularity="DAILY")
    return [{**row, "provider": row.get("provider") or provider} for row in rows]


async def _read_cached_payload(cache_key: str) -> Dict[str, Any] | None:
    cache = get_cache_service()
    if not cache.enabled:
        return None
    cached_payload = await cache.get(cache_key)
    if isinstance(cached_payload, dict):
        return cached_payload
    return None


async def _store_cached_payload(
    cache_key: str,
    payload: Dict[str, Any],
    ttl: timedelta,
) -> None:
    cache = get_cache_service()
    if not cache.enabled:
        return
    await cache.set(cache_key, payload, ttl=ttl)


@router.get("")
async def get_carbon_footprint(
    start_date: date,
    end_date: date,
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    db: AsyncSession = Depends(get_db),
    region: str = "us-east-1",
    provider: str = "aws",
) -> Dict[str, Any]:
    """Calculates the estimated CO2 emissions. Requires Growth tier or higher."""
    if (end_date - start_date).days > 366:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 1 year")

    tenant_id = _require_tenant_id(user)
    normalized_provider = _normalize_provider(provider)
    cache_key = (
        f"api:carbon:footprint:{tenant_id}:{normalized_provider}:{region}:"
        f"{start_date.isoformat()}:{end_date.isoformat()}"
    )
    cached = await _read_cached_payload(cache_key)
    if cached is not None:
        return cached

    connection = await _get_provider_connection(db, tenant_id, normalized_provider)

    if not connection:
        raise HTTPException(
            400, f"No active {normalized_provider.upper()} connection found"
        )

    cost_data = await _fetch_provider_cost_data(
        connection, normalized_provider, start_date, end_date
    )
    factor_payload = await CarbonFactorService(db).get_active_payload()
    calculator = CarbonCalculator(factor_payload)
    payload = calculator.calculate_from_costs(
        cost_data, region=region, provider=normalized_provider
    )
    await _store_cached_payload(cache_key, payload, ttl=CARBON_FOOTPRINT_CACHE_TTL)
    return payload


@router.get("/budget")
async def get_carbon_budget(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    db: AsyncSession = Depends(get_db),
    region: str = "us-east-1",
    provider: str = "aws",
) -> Dict[str, Any]:
    """Get carbon budget status for the current month."""
    tenant_id = _require_tenant_id(user)
    normalized_provider = _normalize_provider(provider)
    today = date.today()
    cache_key = f"api:carbon:budget:{tenant_id}:{normalized_provider}:{region}:{today.isoformat()}"
    cached = await _read_cached_payload(cache_key)
    if cached is not None:
        return cached

    connection = await _get_provider_connection(db, tenant_id, normalized_provider)

    if not connection:
        payload = {
            "error": f"No active {normalized_provider.upper()} connection found",
            "alert_status": "unknown",
        }
        await _store_cached_payload(cache_key, payload, ttl=CARBON_BUDGET_CACHE_TTL)
        return payload

    month_start = date(today.year, today.month, 1)

    settings_result = await db.execute(
        select(CarbonSettings).where(CarbonSettings.tenant_id == tenant_id).limit(1)
    )
    carbon_settings = settings_result.scalar_one_or_none()

    calc_region = region
    if (
        carbon_settings
        and region == "us-east-1"
        and carbon_settings.default_region != "us-east-1"
    ):
        calc_region = carbon_settings.default_region

    cost_data = await _fetch_provider_cost_data(
        connection, normalized_provider, month_start, today
    )

    factor_payload = await CarbonFactorService(db).get_active_payload()
    calculator = CarbonCalculator(factor_payload)
    carbon_result = calculator.calculate_from_costs(
        cost_data,
        region=calc_region,
        provider=normalized_provider,
    )

    budget_service = CarbonBudgetService(db)
    budget_status = await budget_service.get_budget_status(
        tenant_id=tenant_id,
        month_start=month_start,
        current_co2_kg=carbon_result["total_co2_kg"],
    )

    if budget_status["alert_status"] in ["warning", "exceeded"]:
        await budget_service.send_carbon_alert(tenant_id, budget_status)

    await _store_cached_payload(cache_key, budget_status, ttl=CARBON_BUDGET_CACHE_TTL)
    return budget_status


@router.get("/graviton")
async def analyze_graviton_opportunities(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
) -> Dict[str, Any]:
    """Analyze EC2 instances for Graviton migration opportunities (AWS only)."""
    tenant_id = _require_tenant_id(user)
    cache_key = f"api:carbon:graviton:{tenant_id}:{region}"
    cached = await _read_cached_payload(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == tenant_id).limit(1)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        payload = {"error": "No AWS connection found", "migration_candidates": 0}
        await _store_cached_payload(cache_key, payload, ttl=CARBON_GRAVITON_CACHE_TTL)
        return payload

    adapter = MultiTenantAWSAdapter(connection)
    credentials = await adapter.get_credentials()

    analyzer = GravitonAnalyzer(credentials=credentials, region=region)
    payload = await analyzer.analyze_instances()
    await _store_cached_payload(cache_key, payload, ttl=CARBON_GRAVITON_CACHE_TTL)
    return payload


@router.get("/intensity")
async def get_carbon_intensity_forecast(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    region: str = Query(default="us-east-1"),
    hours: int = Query(default=24, ge=1, le=72),
) -> Dict[str, Any]:
    """Get current and forecasted carbon intensity for a region."""
    cache_key = f"api:carbon:intensity:{region}:{hours}"
    cached = await _read_cached_payload(cache_key)
    if cached is not None:
        return cached

    settings = get_settings()
    scheduler = CarbonAwareScheduler(
        wattime_key=settings.WATT_TIME_API_KEY,
        electricitymaps_key=settings.ELECTRICITY_MAPS_API_KEY,
    )

    forecast, current_intensity = await asyncio.gather(
        scheduler.get_intensity_forecast(region, hours),
        scheduler.get_region_intensity(region),
    )
    payload = {
        "region": region,
        "current_intensity": current_intensity,
        "forecast": forecast,
        "source": "api" if not scheduler._use_static_data else "simulation",
    }
    await _store_cached_payload(cache_key, payload, ttl=CARBON_INTENSITY_CACHE_TTL)
    return payload


@router.get("/schedule")
async def get_green_schedule(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    region: str = Query(default="us-east-1"),
    duration_hours: int = Query(default=1, ge=1, le=24),
) -> Dict[str, Any]:
    """Find the optimal execution time for a workload."""
    cache_key = f"api:carbon:schedule:{region}:{duration_hours}"
    cached = await _read_cached_payload(cache_key)
    if cached is not None:
        return cached

    settings = get_settings()
    scheduler = CarbonAwareScheduler(
        wattime_key=settings.WATT_TIME_API_KEY,
        electricitymaps_key=settings.ELECTRICITY_MAPS_API_KEY,
    )

    optimal_time = await scheduler.get_optimal_execution_time(region)
    payload = {
        "region": region,
        "optimal_start_time": optimal_time.isoformat() if optimal_time else None,
        "recommendation": (
            "Execute now"
            if not optimal_time
            else f"Defer to {optimal_time.hour}:00 UTC for lowest carbon footprint"
        ),
    }
    await _store_cached_payload(cache_key, payload, ttl=CARBON_SCHEDULE_CACHE_TTL)
    return payload


@router.get("/factors/active", response_model=CarbonFactorSetItem)
async def get_active_carbon_factor_set(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
) -> CarbonFactorSetItem:
    service = CarbonFactorService(db)
    active = await service.ensure_active()
    return _factor_set_to_item(active)


@router.get("/factors", response_model=CarbonFactorSetListResponse)
async def list_carbon_factor_sets(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CarbonFactorSetListResponse:
    rows = (
        (
            await db.execute(
                select(CarbonFactorSet)
                .order_by(desc(CarbonFactorSet.created_at))
                .limit(int(limit))
            )
        )
        .scalars()
        .all()
    )
    items = [_factor_set_to_item(row) for row in rows]
    return CarbonFactorSetListResponse(total=len(items), items=items)


@router.get("/factors/updates", response_model=CarbonFactorUpdateLogListResponse)
async def list_carbon_factor_update_logs(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CarbonFactorUpdateLogListResponse:
    rows = (
        (
            await db.execute(
                select(CarbonFactorUpdateLog)
                .order_by(desc(CarbonFactorUpdateLog.recorded_at))
                .limit(int(limit))
            )
        )
        .scalars()
        .all()
    )
    items = [_update_log_to_item(row) for row in rows]
    return CarbonFactorUpdateLogListResponse(total=len(items), items=items)


@router.post("/factors", response_model=CarbonFactorSetItem)
async def stage_carbon_factor_set(
    request: CarbonFactorStageRequest,
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
) -> CarbonFactorSetItem:
    service = CarbonFactorService(db)
    staged = await service.stage(
        request.payload,
        actor_user_id=user.id,
        message=request.message,
    )
    await db.commit()
    return _factor_set_to_item(staged)


@router.post("/factors/{factor_set_id}/activate", response_model=CarbonFactorSetItem)
async def activate_carbon_factor_set(
    factor_set_id: UUID,
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
) -> CarbonFactorSetItem:
    factor_set = await db.scalar(
        select(CarbonFactorSet).where(CarbonFactorSet.id == factor_set_id)
    )
    if factor_set is None:
        raise HTTPException(status_code=404, detail="Carbon factor set not found.")
    service = CarbonFactorService(db)
    activated = await service.activate(
        factor_set,
        actor_user_id=user.id,
        action="manual_activated",
        message="Manually activated via API.",
    )
    await db.commit()
    return _factor_set_to_item(activated)


@router.post("/factors/auto-activate")
async def auto_activate_latest_carbon_factors(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.CARBON_ASSURANCE, required_role="admin")),
    ],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    service = CarbonFactorService(db)
    result = await service.auto_activate_latest()
    await db.commit()
    return result
