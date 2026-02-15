from typing import Annotated, Any, Dict, List
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.shared.core.auth import CurrentUser, require_tenant_access
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db
from app.modules.optimization.domain.service import OptimizationService
from app.models.optimization import (
    StrategyRecommendation,
    CommitmentTerm,
    PaymentOption,
    OptimizationStrategy,
)
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger

router = APIRouter(tags=["FinOps Strategy (RI/SP)"])


# --- Schemas ---
class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_type: str
    region: str
    term: CommitmentTerm
    payment_option: PaymentOption
    upfront_cost: float
    monthly_recurring_cost: float
    estimated_monthly_savings_low: float | None = None
    estimated_monthly_savings: float
    estimated_monthly_savings_high: float | None = None
    roi_percentage: float
    break_even_months: float | None = None
    confidence_score: float | None = None
    status: str


class OptimizationScanResponse(BaseModel):
    status: str
    recommendations_generated: int
    message: str


class StrategyBacktestRead(BaseModel):
    strategy_id: UUID
    name: str
    provider: str
    strategy_type: str
    usage_summary: Dict[str, Any]
    backtest: Dict[str, Any]


class StrategyBacktestResponse(BaseModel):
    status: str
    strategies: List[StrategyBacktestRead]


# --- Endpoints ---


@router.get("/recommendations", response_model=List[RecommendationRead])
async def list_recommendations(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser, Depends(requires_feature(FeatureFlag.COMMITMENT_OPTIMIZATION))
    ],
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="open"),
) -> Any:
    """
    List FinOps optimization recommendations for the tenant.
    """
    q = (
        select(StrategyRecommendation)
        .where(
            StrategyRecommendation.tenant_id == tenant_id,
            StrategyRecommendation.status == status,
        )
        .order_by(StrategyRecommendation.estimated_monthly_savings.desc())
    )

    result = await db.execute(q)
    return result.scalars().all()


@router.post("/refresh", response_model=OptimizationScanResponse)
async def trigger_optimization_scan(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMMITMENT_OPTIMIZATION, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> OptimizationScanResponse:
    """
    Trigger a fresh analysis of cloud usage to generate RI/SP recommendations.
    """
    service = OptimizationService(db=db)
    recs = await service.generate_recommendations(tenant_id)

    return OptimizationScanResponse(
        status="success",
        recommendations_generated=len(recs),
        message=f"Generated {len(recs)} new optimization opportunities.",
    )


@router.get("/backtest", response_model=StrategyBacktestResponse)
async def backtest_strategies(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser, Depends(requires_feature(FeatureFlag.COMMITMENT_OPTIMIZATION))
    ],
    db: AsyncSession = Depends(get_db),
    provider: str | None = Query(
        default=None, description="Optional provider filter (aws|azure|gcp)"
    ),
    strategy_type: str | None = Query(
        default=None,
        description="Optional strategy type filter (savings_plan|reserved_instance|committed_use_discount|azure_reservation)",
    ),
    days: int = Query(default=30, ge=7, le=365),
) -> StrategyBacktestResponse:
    """
    Deterministically backtest the commitment baseline projection against recent ledger history.

    This endpoint is an operator/finance tool:
    - It does NOT purchase commitments.
    - It is safe to run repeatedly (read-only).
    """
    _ = user  # dependency enforces tier gating
    service = OptimizationService(db=db)

    query = select(OptimizationStrategy).where(OptimizationStrategy.is_active.is_(True))
    if provider:
        query = query.where(OptimizationStrategy.provider == provider.strip().lower())
    if strategy_type:
        query = query.where(OptimizationStrategy.type == strategy_type.strip().lower())

    result = await db.execute(query)
    strategies = list(result.scalars().all())
    if not strategies:
        strategies = await service._seed_default_strategies()

    out: list[StrategyBacktestRead] = []
    for strat in strategies:
        impl = service._get_strategy_impl(strat)
        if impl is None:
            continue

        provider_key = (
            str(getattr(strat, "provider", "") or "").strip().lower() or "unknown"
        )
        raw_type = getattr(strat, "type", None)
        type_value = (
            raw_type.value
            if raw_type is not None and hasattr(raw_type, "value")
            else str(raw_type or "")
        )
        type_key = type_value.strip().lower() or "unknown"

        canonical_charge_category = (
            "compute"
            if type_key
            in {
                "savings_plan",
                "reserved_instance",
                "committed_use_discount",
                "azure_reservation",
            }
            else None
        )
        usage_data = await service._aggregate_usage(
            tenant_id,
            provider=provider_key if provider_key != "unknown" else None,
            canonical_charge_category=canonical_charge_category,
            lookback_days=days,
        )
        hourly_series = (
            usage_data.get("hourly_cost_series")
            if isinstance(usage_data, dict)
            else None
        )

        tolerance = 0.30
        cfg = getattr(strat, "config", None)
        if isinstance(cfg, dict) and "backtest_tolerance" in cfg:
            try:
                tolerance = float(cfg.get("backtest_tolerance") or tolerance)
            except Exception:
                tolerance = 0.30

        backtest: Dict[str, Any] = {"reason": "no_series"}
        if (
            hasattr(impl, "backtest_hourly_series")
            and isinstance(hourly_series, list)
            and hourly_series
        ):
            backtest = impl.backtest_hourly_series(hourly_series, tolerance=tolerance)

        usage_summary = {
            "provider": usage_data.get("provider"),
            "canonical_charge_category": usage_data.get("canonical_charge_category"),
            "granularity": usage_data.get("granularity"),
            "observed_buckets": usage_data.get("observed_buckets"),
            "expected_buckets": usage_data.get("expected_buckets"),
            "coverage_ratio": usage_data.get("coverage_ratio"),
            "volatility": usage_data.get("volatility"),
            "confidence_score": usage_data.get("confidence_score"),
            "baseline_hourly_spend": usage_data.get("baseline_hourly_spend"),
            "average_hourly_spend": usage_data.get("average_hourly_spend"),
            "top_region": usage_data.get("top_region"),
        }

        out.append(
            StrategyBacktestRead(
                strategy_id=strat.id,
                name=strat.name,
                provider=provider_key,
                strategy_type=type_key,
                usage_summary=usage_summary,
                backtest=backtest,
            )
        )

    return StrategyBacktestResponse(status="success", strategies=out)


@router.post("/apply/{recommendation_id}")
async def apply_recommendation(
    request: Request,
    recommendation_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMMITMENT_OPTIMIZATION, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """
    Mark a recommendation as applied.
    (Future: Trigger cloud API calls to purchase RI/SP).
    """
    q = select(StrategyRecommendation).where(
        StrategyRecommendation.id == recommendation_id,
        StrategyRecommendation.tenant_id == tenant_id,
    )
    result = await db.execute(q)
    rec = result.scalar_one_or_none()

    if not rec:
        from app.shared.core.exceptions import ResourceNotFoundError

        raise ResourceNotFoundError("Recommendation not found")

    rec.status = "applied"
    rec.applied_at = datetime.now(timezone.utc)

    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.OPTIMIZATION_RECOMMENDATION_APPLIED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="strategy_recommendation",
        resource_id=str(recommendation_id),
        details={
            "strategy_id": str(rec.strategy_id),
            "estimated_monthly_savings": float(rec.estimated_monthly_savings or 0.0),
            "region": rec.region,
            "resource_type": rec.resource_type,
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )

    await db.commit()

    return {"status": "applied", "recommendation_id": str(recommendation_id)}
