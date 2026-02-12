from datetime import date, datetime, time, timezone
from typing import Annotated, Any, Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.carbon_settings import CarbonSettings
from app.models.gcp_connection import GCPConnection
from app.modules.reporting.domain.budget_alerts import CarbonBudgetService
from app.modules.reporting.domain.calculator import CarbonCalculator
from app.modules.reporting.domain.carbon_scheduler import CarbonAwareScheduler
from app.modules.reporting.domain.graviton_analyzer import GravitonAnalyzer
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db

router = APIRouter(tags=["GreenOps & Carbon"])
logger = structlog.get_logger()
SUPPORTED_CARBON_PROVIDERS = {"aws", "azure", "gcp"}


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
            .where(AzureConnection.tenant_id == tenant_id, AzureConnection.is_active.is_(True))
            .limit(1)
        )
        return result.scalar_one_or_none()

    result = await db.execute(
        (
            select(GCPConnection)
            .where(GCPConnection.tenant_id == tenant_id, GCPConnection.is_active.is_(True))
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
    connection = await _get_provider_connection(db, tenant_id, normalized_provider)

    if not connection:
        raise HTTPException(400, f"No active {normalized_provider.upper()} connection found")

    cost_data = await _fetch_provider_cost_data(connection, normalized_provider, start_date, end_date)
    calculator = CarbonCalculator()
    return calculator.calculate_from_costs(cost_data, region=region, provider=normalized_provider)


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
    connection = await _get_provider_connection(db, tenant_id, normalized_provider)

    if not connection:
        return {
            "error": f"No active {normalized_provider.upper()} connection found",
            "alert_status": "unknown",
        }

    today = date.today()
    month_start = date(today.year, today.month, 1)

    settings_result = await db.execute(
        select(CarbonSettings).where(CarbonSettings.tenant_id == tenant_id).limit(1)
    )
    carbon_settings = settings_result.scalar_one_or_none()

    calc_region = region
    if carbon_settings and region == "us-east-1" and carbon_settings.default_region != "us-east-1":
        calc_region = carbon_settings.default_region

    cost_data = await _fetch_provider_cost_data(connection, normalized_provider, month_start, today)

    calculator = CarbonCalculator()
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

    return budget_status


@router.get("/graviton")
async def analyze_graviton_opportunities(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
) -> Dict[str, Any]:
    """Analyze EC2 instances for Graviton migration opportunities (AWS only)."""
    tenant_id = _require_tenant_id(user)
    result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id).limit(1))
    connection = result.scalar_one_or_none()

    if not connection:
        return {"error": "No AWS connection found", "migration_candidates": 0}

    adapter = MultiTenantAWSAdapter(connection)
    credentials = await adapter.get_credentials()

    analyzer = GravitonAnalyzer(credentials=credentials, region=region)
    return await analyzer.analyze_instances()


@router.get("/intensity")
async def get_carbon_intensity_forecast(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    region: str = Query(default="us-east-1"),
    hours: int = Query(default=24, ge=1, le=72),
) -> Dict[str, Any]:
    """Get current and forecasted carbon intensity for a region."""
    settings = get_settings()
    scheduler = CarbonAwareScheduler(
        wattime_key=settings.WATT_TIME_API_KEY,
        electricitymaps_key=settings.ELECTRICITY_MAPS_API_KEY,
    )

    forecast = await scheduler.get_intensity_forecast(region, hours)
    return {
        "region": region,
        "current_intensity": await scheduler.get_region_intensity(region),
        "forecast": forecast,
        "source": "api" if not scheduler._use_static_data else "simulation",
    }


@router.get("/schedule")
async def get_green_schedule(
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GREENOPS))],
    region: str = Query(default="us-east-1"),
    duration_hours: int = Query(default=1, ge=1, le=24),
) -> Dict[str, Any]:
    """Find the optimal execution time for a workload."""
    settings = get_settings()
    scheduler = CarbonAwareScheduler(
        wattime_key=settings.WATT_TIME_API_KEY,
        electricitymaps_key=settings.ELECTRICITY_MAPS_API_KEY,
    )

    optimal_time = await scheduler.get_optimal_execution_time(region)
    return {
        "region": region,
        "optimal_start_time": optimal_time.isoformat() if optimal_time else None,
        "recommendation": (
            "Execute now"
            if not optimal_time
            else f"Defer to {optimal_time.hour}:00 UTC for lowest carbon footprint"
        ),
    }
