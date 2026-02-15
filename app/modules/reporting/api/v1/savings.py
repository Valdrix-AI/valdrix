"""
Savings Proof API

Provides a procurement-friendly view of:
- Current savings opportunity (open recommendations + pending remediations)
- Estimated realized savings (applied recommendations + completed remediations) over a window

Notes:
- "Realized" here is estimated monthly savings based on recommendation/remediation metadata.
  Finance-grade realized savings requires post-action billing deltas and attribution, which
  should be layered in as the ledger matures.
"""

from __future__ import annotations

from datetime import date, timedelta
from datetime import datetime, time, timezone
from typing import Any, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.shared.core.auth import CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag, PricingTier, normalize_tier
from app.shared.db.session import get_db
from app.modules.reporting.domain.savings_proof import (
    SavingsProofDrilldownResponse,
    SavingsProofResponse,
    SavingsProofService,
)
from app.modules.reporting.domain.realized_savings import RealizedSavingsService
from app.models.remediation import RemediationRequest, RemediationStatus
from app.models.realized_savings import RealizedSavingsEvent

logger = structlog.get_logger()
router = APIRouter(tags=["Savings Proof"])


def _require_tenant_id(user: CurrentUser) -> UUID:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required.")
    return user.tenant_id


@router.get("/proof", response_model=SavingsProofResponse)
async def get_savings_proof(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.SAVINGS_PROOF)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE_TRIAL))
    normalized_provider = provider.strip().lower() if provider else None
    service = SavingsProofService(db)
    try:
        payload = await service.generate(
            tenant_id=tenant_id,
            tier=tier.value,
            start_date=start_date,
            end_date=end_date,
            provider=normalized_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if response_format == "csv":
        csv_data = SavingsProofService.render_csv(payload)
        filename = f"savings-proof-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


@router.get("/proof/drilldown", response_model=SavingsProofDrilldownResponse)
async def get_savings_proof_drilldown(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    dimension: str = Query(
        default="strategy_type", pattern="^(provider|strategy_type|remediation_action)$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.SAVINGS_PROOF)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    tenant_id = _require_tenant_id(current_user)
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE_TRIAL))
    normalized_provider = provider.strip().lower() if provider else None
    service = SavingsProofService(db)
    try:
        payload = await service.drilldown(
            tenant_id=tenant_id,
            tier=tier.value,
            start_date=start_date,
            end_date=end_date,
            provider=normalized_provider,
            dimension=dimension,
            limit=int(limit),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if response_format == "csv":
        csv_data = SavingsProofService.render_drilldown_csv(payload)
        filename = f"savings-proof-drilldown-{payload.dimension}-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


class RealizedSavingsComputeResponse(BaseModel):
    computed: int
    skipped: int
    errors: list[dict[str, Any]]


@router.post("/realized/compute", response_model=RealizedSavingsComputeResponse)
async def compute_realized_savings(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=60)),
    end_date: date = Query(default_factory=date.today),
    baseline_days: int = Query(default=7, ge=1, le=31),
    measurement_days: int = Query(default=7, ge=1, le=31),
    gap_days: int = Query(default=1, ge=0, le=7),
    monthly_multiplier_days: int = Query(default=30, ge=1, le=31),
    require_final: bool = Query(default=True),
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SAVINGS_PROOF, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> RealizedSavingsComputeResponse:
    """
    Compute and persist realized savings evidence for completed remediations.

    This is an operator/admin endpoint. It writes RealizedSavingsEvent rows that
    are later used by the Savings Proof report (finance-grade deltas where available).
    """
    tenant_id = _require_tenant_id(current_user)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    window_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    stmt = select(RemediationRequest).where(
        RemediationRequest.tenant_id == tenant_id,
        RemediationRequest.status == RemediationStatus.COMPLETED.value,
        RemediationRequest.executed_at.is_not(None),
        RemediationRequest.executed_at >= window_start,
        RemediationRequest.executed_at <= window_end,
    )
    remediations = list((await db.execute(stmt)).scalars().all())

    service = RealizedSavingsService(db)
    computed = 0
    skipped = 0
    errors: list[dict[str, Any]] = []
    for request in remediations:
        try:
            event = await service.compute_for_request(
                tenant_id=tenant_id,
                request=request,
                baseline_days=int(baseline_days),
                measurement_days=int(measurement_days),
                gap_days=int(gap_days),
                monthly_multiplier_days=int(monthly_multiplier_days),
                require_final=bool(require_final),
            )
            if event is None:
                skipped += 1
            else:
                computed += 1
        except Exception as exc:  # noqa: BLE001 - operator endpoint should report partial results
            errors.append(
                {"request_id": str(getattr(request, "id", "")), "error": str(exc)}
            )

    await db.commit()

    logger.info(
        "realized_savings_compute_completed",
        tenant_id=str(tenant_id),
        computed=computed,
        skipped=skipped,
        errors=len(errors),
    )
    return RealizedSavingsComputeResponse(
        computed=computed, skipped=skipped, errors=errors
    )


class RealizedSavingsEventResponse(BaseModel):
    remediation_request_id: str
    provider: str
    account_id: str | None
    resource_id: str | None
    region: str | None
    method: str
    executed_at: str | None
    baseline_start_date: str
    baseline_end_date: str
    measurement_start_date: str
    measurement_end_date: str
    baseline_avg_daily_cost_usd: float
    measurement_avg_daily_cost_usd: float
    realized_monthly_savings_usd: float
    confidence_score: float | None
    computed_at: str


@router.get("/realized/events", response_model=list[RealizedSavingsEventResponse])
async def list_realized_savings_events(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = Query(
        default=None, pattern="^(aws|azure|gcp|saas|license|platform|hybrid)$"
    ),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    limit: int = Query(default=200, ge=1, le=5000),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.SAVINGS_PROOF)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    List realized savings evidence events for completed remediations.

    Window filters are based on the remediation executed_at timestamp.
    """
    tenant_id = _require_tenant_id(current_user)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    window_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    normalized_provider = provider.strip().lower() if provider else None

    stmt = (
        select(RealizedSavingsEvent, RemediationRequest.executed_at)
        .join(
            RemediationRequest,
            RealizedSavingsEvent.remediation_request_id == RemediationRequest.id,
        )
        .where(
            RealizedSavingsEvent.tenant_id == tenant_id,
            RemediationRequest.executed_at.is_not(None),
            RemediationRequest.executed_at >= window_start,
            RemediationRequest.executed_at <= window_end,
        )
        .order_by(
            RealizedSavingsEvent.realized_monthly_savings_usd.desc(),
            RealizedSavingsEvent.computed_at.desc(),
        )
        .limit(int(limit))
    )
    if normalized_provider:
        stmt = stmt.where(RealizedSavingsEvent.provider == normalized_provider)

    rows = list((await db.execute(stmt)).all())
    events: list[RealizedSavingsEventResponse] = []
    for event, executed_at in rows:
        events.append(
            RealizedSavingsEventResponse(
                remediation_request_id=str(event.remediation_request_id),
                provider=str(event.provider),
                account_id=str(event.account_id) if event.account_id else None,
                resource_id=str(event.resource_id) if event.resource_id else None,
                region=str(event.region) if event.region else None,
                method=str(event.method),
                executed_at=executed_at.isoformat()
                if isinstance(executed_at, datetime)
                else None,
                baseline_start_date=event.baseline_start_date.isoformat(),
                baseline_end_date=event.baseline_end_date.isoformat(),
                measurement_start_date=event.measurement_start_date.isoformat(),
                measurement_end_date=event.measurement_end_date.isoformat(),
                baseline_avg_daily_cost_usd=float(
                    event.baseline_avg_daily_cost_usd or 0
                ),
                measurement_avg_daily_cost_usd=float(
                    event.measurement_avg_daily_cost_usd or 0
                ),
                realized_monthly_savings_usd=float(
                    event.realized_monthly_savings_usd or 0
                ),
                confidence_score=float(event.confidence_score)
                if event.confidence_score is not None
                else None,
                computed_at=event.computed_at.isoformat(),
            )
        )

    if response_format == "csv":
        header = [
            "remediation_request_id",
            "provider",
            "account_id",
            "resource_id",
            "region",
            "method",
            "executed_at",
            "baseline_start_date",
            "baseline_end_date",
            "measurement_start_date",
            "measurement_end_date",
            "baseline_avg_daily_cost_usd",
            "measurement_avg_daily_cost_usd",
            "realized_monthly_savings_usd",
            "confidence_score",
            "computed_at",
        ]
        lines = [",".join(header)]
        for item in events:
            row = item.model_dump()
            lines.append(",".join([str(row.get(col, "") or "") for col in header]))
        filename = (
            f"realized-savings-{start_date.isoformat()}-{end_date.isoformat()}.csv"
        )
        return Response(
            content="\n".join(lines) + "\n",
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return events
