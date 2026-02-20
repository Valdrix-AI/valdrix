"""
Savings Proof (Domain)

Provides a procurement-friendly view of:
- Current savings opportunity (open recommendations + pending remediations)
- Estimated realized savings (applied recommendations + completed remediations) over a window

Notes:
- "Realized" here is estimated monthly savings based on recommendation/remediation metadata.
  Finance-grade realized savings requires post-action billing deltas and attribution, which
  should be layered in as the ledger matures.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.optimization import OptimizationStrategy, StrategyRecommendation
from app.models.realized_savings import RealizedSavingsEvent
from app.models.remediation import RemediationRequest, RemediationStatus

logger = structlog.get_logger()


def _as_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SavingsProofBreakdownItem(BaseModel):
    provider: str
    opportunity_monthly_usd: float
    realized_monthly_usd: float
    open_recommendations: int
    applied_recommendations: int
    pending_remediations: int
    completed_remediations: int


class SavingsProofResponse(BaseModel):
    start_date: str
    end_date: str
    as_of: str
    tier: str
    opportunity_monthly_usd: float
    realized_monthly_usd: float
    open_recommendations: int
    applied_recommendations: int
    pending_remediations: int
    completed_remediations: int
    breakdown: list[SavingsProofBreakdownItem]
    notes: list[str]


class SavingsProofDrilldownBucket(BaseModel):
    key: str
    opportunity_monthly_usd: float
    realized_monthly_usd: float
    open_recommendations: int
    applied_recommendations: int
    pending_remediations: int
    completed_remediations: int


class SavingsProofDrilldownResponse(BaseModel):
    start_date: str
    end_date: str
    as_of: str
    tier: str
    provider: str | None
    dimension: str
    opportunity_monthly_usd: float
    realized_monthly_usd: float
    buckets: list[SavingsProofDrilldownBucket]
    truncated: bool
    limit: int
    notes: list[str]


class SavingsProofService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate(
        self,
        *,
        tenant_id: UUID,
        tier: str,
        start_date: date,
        end_date: date,
        provider: Optional[str] = None,
    ) -> SavingsProofResponse:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        now = datetime.now(timezone.utc)
        window_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        window_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        normalized_provider = provider.strip().lower() if provider else None

        # --- Opportunity snapshot (as-of now) ---
        open_recs_stmt = (
            select(StrategyRecommendation, OptimizationStrategy.provider)
            .join(
                OptimizationStrategy,
                StrategyRecommendation.strategy_id == OptimizationStrategy.id,
            )
            .where(
                StrategyRecommendation.tenant_id == tenant_id,
                StrategyRecommendation.status == "open",
            )
        )
        open_recs_rows = list((await self.db.execute(open_recs_stmt)).all())

        pending_statuses = {
            RemediationStatus.PENDING.value,
            RemediationStatus.PENDING_APPROVAL.value,
            RemediationStatus.APPROVED.value,
            RemediationStatus.SCHEDULED.value,
            RemediationStatus.EXECUTING.value,
        }
        pending_stmt = select(RemediationRequest).where(
            RemediationRequest.tenant_id == tenant_id,
            RemediationRequest.status.in_(pending_statuses),
        )
        pending_rems = list((await self.db.execute(pending_stmt)).scalars().all())

        # --- Realized in window ---
        applied_stmt = (
            select(StrategyRecommendation, OptimizationStrategy.provider)
            .join(
                OptimizationStrategy,
                StrategyRecommendation.strategy_id == OptimizationStrategy.id,
            )
            .where(
                StrategyRecommendation.tenant_id == tenant_id,
                StrategyRecommendation.status == "applied",
                StrategyRecommendation.applied_at.is_not(None),
                StrategyRecommendation.applied_at >= window_start,
                StrategyRecommendation.applied_at <= window_end,
            )
        )
        applied_rows = list((await self.db.execute(applied_stmt)).all())

        completed_stmt = select(RemediationRequest).where(
            RemediationRequest.tenant_id == tenant_id,
            RemediationRequest.status == RemediationStatus.COMPLETED.value,
        )
        completed_rems_all = list(
            (await self.db.execute(completed_stmt)).scalars().all()
        )
        completed_rems: list[RemediationRequest] = []
        for item in completed_rems_all:
            completed_at = _as_utc_datetime(
                item.executed_at or item.updated_at or item.created_at
            )
            if completed_at is None:
                continue
            if window_start <= completed_at <= window_end:
                completed_rems.append(item)

        # Provider filter (optional)
        if normalized_provider:
            open_recs_rows = [
                row
                for row in open_recs_rows
                if str(row[1]).lower() == normalized_provider
            ]
            applied_rows = [
                row
                for row in applied_rows
                if str(row[1]).lower() == normalized_provider
            ]
            pending_rems = [
                row
                for row in pending_rems
                if str(row.provider).lower() == normalized_provider
            ]
            completed_rems = [
                row
                for row in completed_rems
                if str(row.provider).lower() == normalized_provider
            ]

        providers = {"aws", "azure", "gcp", "saas", "license", "platform", "hybrid"}
        if normalized_provider:
            providers = {normalized_provider}

        realized_events: dict[UUID, RealizedSavingsEvent] = {}
        if completed_rems:
            event_stmt = select(RealizedSavingsEvent).where(
                RealizedSavingsEvent.tenant_id == tenant_id,
                RealizedSavingsEvent.remediation_request_id.in_(
                    [rem.id for rem in completed_rems]
                ),
            )
            realized_events = {
                item.remediation_request_id: item
                for item in list((await self.db.execute(event_stmt)).scalars().all())
            }

        breakdown: dict[str, dict[str, Any]] = {
            p: {
                "opportunity_monthly_usd": 0.0,
                "realized_monthly_usd": 0.0,
                "open_recommendations": 0,
                "applied_recommendations": 0,
                "pending_remediations": 0,
                "completed_remediations": 0,
            }
            for p in sorted(providers)
        }

        for rec, rec_provider in open_recs_rows:
            p = str(rec_provider).lower()
            if p not in breakdown:
                continue
            breakdown[p]["open_recommendations"] += 1
            breakdown[p]["opportunity_monthly_usd"] += _as_float(
                rec.estimated_monthly_savings
            )

        for rec, rec_provider in applied_rows:
            p = str(rec_provider).lower()
            if p not in breakdown:
                continue
            breakdown[p]["applied_recommendations"] += 1
            breakdown[p]["realized_monthly_usd"] += _as_float(
                rec.estimated_monthly_savings
            )

        for rem in pending_rems:
            p = str(rem.provider).lower()
            if p not in breakdown:
                continue
            breakdown[p]["pending_remediations"] += 1
            breakdown[p]["opportunity_monthly_usd"] += _as_float(
                rem.estimated_monthly_savings
            )

        for rem in completed_rems:
            p = str(rem.provider).lower()
            if p not in breakdown:
                continue
            breakdown[p]["completed_remediations"] += 1
            realized_event = realized_events.get(rem.id)
            if realized_event is not None:
                breakdown[p]["realized_monthly_usd"] += _as_float(
                    realized_event.realized_monthly_savings_usd
                )
            else:
                breakdown[p]["realized_monthly_usd"] += _as_float(
                    rem.estimated_monthly_savings
                )

        breakdown_items = [
            SavingsProofBreakdownItem(provider=p, **values)
            for p, values in breakdown.items()
        ]
        opportunity_total = sum(
            item.opportunity_monthly_usd for item in breakdown_items
        )
        realized_total = sum(item.realized_monthly_usd for item in breakdown_items)
        open_recs_count = sum(item.open_recommendations for item in breakdown_items)
        applied_recs_count = sum(
            item.applied_recommendations for item in breakdown_items
        )
        pending_rems_count = sum(item.pending_remediations for item in breakdown_items)
        completed_rems_count = sum(
            item.completed_remediations for item in breakdown_items
        )

        payload = SavingsProofResponse(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            as_of=now.isoformat(),
            tier=str(tier),
            opportunity_monthly_usd=round(opportunity_total, 2),
            realized_monthly_usd=round(realized_total, 2),
            open_recommendations=open_recs_count,
            applied_recommendations=applied_recs_count,
            pending_remediations=pending_rems_count,
            completed_remediations=completed_rems_count,
            breakdown=breakdown_items,
            notes=[
                "Opportunity is a snapshot of currently open recommendations/pending remediations.",
                "Realized savings uses finance-grade ledger deltas where evidence exists; otherwise it falls back to estimated monthly savings.",
            ],
        )

        logger.info(
            "savings_proof_generated",
            tenant_id=str(tenant_id),
            provider=normalized_provider,
            start_date=payload.start_date,
            end_date=payload.end_date,
            opportunity_monthly_usd=payload.opportunity_monthly_usd,
            realized_monthly_usd=payload.realized_monthly_usd,
        )

        return payload

    async def drilldown(
        self,
        *,
        tenant_id: UUID,
        tier: str,
        start_date: date,
        end_date: date,
        dimension: str,
        provider: Optional[str] = None,
        limit: int = 50,
    ) -> SavingsProofDrilldownResponse:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        dim = str(dimension or "").strip().lower()
        normalized_provider = provider.strip().lower() if provider else None

        supported_dims = {"provider", "strategy_type", "remediation_action"}
        if dim not in supported_dims:
            supported = ", ".join(sorted(supported_dims))
            raise ValueError(
                f"Unsupported drilldown dimension '{dimension}'. Use one of: {supported}"
            )

        top_limit = max(1, min(int(limit), 200))

        now = datetime.now(timezone.utc)
        window_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        window_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        # "provider" drilldown is just a reshaped SavingsProofResponse breakdown.
        if dim == "provider":
            summary = await self.generate(
                tenant_id=tenant_id,
                tier=tier,
                start_date=start_date,
                end_date=end_date,
                provider=normalized_provider,
            )
            buckets = [
                SavingsProofDrilldownBucket(
                    key=item.provider,
                    opportunity_monthly_usd=float(item.opportunity_monthly_usd),
                    realized_monthly_usd=float(item.realized_monthly_usd),
                    open_recommendations=int(item.open_recommendations),
                    applied_recommendations=int(item.applied_recommendations),
                    pending_remediations=int(item.pending_remediations),
                    completed_remediations=int(item.completed_remediations),
                )
                for item in summary.breakdown
            ]
            return SavingsProofDrilldownResponse(
                start_date=summary.start_date,
                end_date=summary.end_date,
                as_of=summary.as_of,
                tier=summary.tier,
                provider=normalized_provider,
                dimension="provider",
                opportunity_monthly_usd=float(summary.opportunity_monthly_usd),
                realized_monthly_usd=float(summary.realized_monthly_usd),
                buckets=buckets,
                truncated=False,
                limit=top_limit,
                notes=summary.notes,
            )

        buckets_by_key: dict[str, dict[str, Any]] = {}

        def _ensure_bucket(key: str) -> dict[str, Any]:
            if key not in buckets_by_key:
                buckets_by_key[key] = {
                    "opportunity_monthly_usd": 0.0,
                    "realized_monthly_usd": 0.0,
                    "open_recommendations": 0,
                    "applied_recommendations": 0,
                    "pending_remediations": 0,
                    "completed_remediations": 0,
                }
            return buckets_by_key[key]

        if dim == "strategy_type":
            # Opportunity: open recommendations (as-of now), grouped by strategy.type.
            open_stmt = (
                select(
                    OptimizationStrategy.type,
                    func.coalesce(
                        func.sum(StrategyRecommendation.estimated_monthly_savings), 0
                    ),
                    func.count(StrategyRecommendation.id),
                )
                .join(
                    OptimizationStrategy,
                    StrategyRecommendation.strategy_id == OptimizationStrategy.id,
                )
                .where(
                    StrategyRecommendation.tenant_id == tenant_id,
                    StrategyRecommendation.status == "open",
                )
                .group_by(OptimizationStrategy.type)
            )
            if normalized_provider:
                open_stmt = open_stmt.where(
                    OptimizationStrategy.provider == normalized_provider
                )
            open_rows = list((await self.db.execute(open_stmt)).all())
            for strategy_type, savings_sum, count in open_rows:
                key = str(getattr(strategy_type, "value", strategy_type)).lower()
                bucket = _ensure_bucket(key)
                bucket["open_recommendations"] += int(count or 0)
                bucket["opportunity_monthly_usd"] += _as_float(savings_sum)

            # Realized: applied recommendations within window, grouped by strategy.type.
            applied_stmt = (
                select(
                    OptimizationStrategy.type,
                    func.coalesce(
                        func.sum(StrategyRecommendation.estimated_monthly_savings), 0
                    ),
                    func.count(StrategyRecommendation.id),
                )
                .join(
                    OptimizationStrategy,
                    StrategyRecommendation.strategy_id == OptimizationStrategy.id,
                )
                .where(
                    StrategyRecommendation.tenant_id == tenant_id,
                    StrategyRecommendation.status == "applied",
                    StrategyRecommendation.applied_at.is_not(None),
                    StrategyRecommendation.applied_at >= window_start,
                    StrategyRecommendation.applied_at <= window_end,
                )
                .group_by(OptimizationStrategy.type)
            )
            if normalized_provider:
                applied_stmt = applied_stmt.where(
                    OptimizationStrategy.provider == normalized_provider
                )
            applied_rows = list((await self.db.execute(applied_stmt)).all())
            for strategy_type, savings_sum, count in applied_rows:
                key = str(getattr(strategy_type, "value", strategy_type)).lower()
                bucket = _ensure_bucket(key)
                bucket["applied_recommendations"] += int(count or 0)
                bucket["realized_monthly_usd"] += _as_float(savings_sum)

            notes = [
                "Opportunity is a snapshot of currently open recommendations, grouped by strategy type.",
                "Realized is applied recommendations within the window (estimated monthly savings).",
            ]

        else:
            # Remediation drilldown by action.
            pending_statuses = {
                RemediationStatus.PENDING.value,
                RemediationStatus.PENDING_APPROVAL.value,
                RemediationStatus.APPROVED.value,
                RemediationStatus.SCHEDULED.value,
                RemediationStatus.EXECUTING.value,
            }

            pending_stmt = (
                select(
                    RemediationRequest.action,
                    func.coalesce(
                        func.sum(RemediationRequest.estimated_monthly_savings), 0
                    ),
                    func.count(RemediationRequest.id),
                )
                .where(
                    RemediationRequest.tenant_id == tenant_id,
                    RemediationRequest.status.in_(pending_statuses),
                )
                .group_by(RemediationRequest.action)
            )
            if normalized_provider:
                pending_stmt = pending_stmt.where(
                    RemediationRequest.provider == normalized_provider
                )
            pending_rows = list((await self.db.execute(pending_stmt)).all())
            for action, savings_sum, count in pending_rows:
                key = str(getattr(action, "value", action)).lower()
                bucket = _ensure_bucket(key)
                bucket["pending_remediations"] += int(count or 0)
                bucket["opportunity_monthly_usd"] += _as_float(savings_sum)

            completed_at = func.coalesce(
                RemediationRequest.executed_at,
                RemediationRequest.updated_at,
                RemediationRequest.created_at,
            )

            # Completed counts (all), grouped by action.
            completed_count_stmt = (
                select(
                    RemediationRequest.action,
                    func.count(RemediationRequest.id),
                )
                .where(
                    RemediationRequest.tenant_id == tenant_id,
                    RemediationRequest.status == RemediationStatus.COMPLETED.value,
                    completed_at >= window_start,
                    completed_at <= window_end,
                )
                .group_by(RemediationRequest.action)
            )
            if normalized_provider:
                completed_count_stmt = completed_count_stmt.where(
                    RemediationRequest.provider == normalized_provider
                )
            completed_count_rows = list(
                (await self.db.execute(completed_count_stmt)).all()
            )
            for action, count in completed_count_rows:
                key = str(getattr(action, "value", action)).lower()
                bucket = _ensure_bucket(key)
                bucket["completed_remediations"] += int(count or 0)

            # Finance-grade realized savings evidence where available (RealizedSavingsEvent).
            evidence_stmt = (
                select(
                    RemediationRequest.action,
                    func.coalesce(
                        func.sum(RealizedSavingsEvent.realized_monthly_savings_usd), 0
                    ),
                )
                .join(
                    RealizedSavingsEvent,
                    (
                        RealizedSavingsEvent.remediation_request_id
                        == RemediationRequest.id
                    )
                    & (RealizedSavingsEvent.tenant_id == RemediationRequest.tenant_id),
                )
                .where(
                    RemediationRequest.tenant_id == tenant_id,
                    RemediationRequest.status == RemediationStatus.COMPLETED.value,
                    completed_at >= window_start,
                    completed_at <= window_end,
                )
                .group_by(RemediationRequest.action)
            )
            if normalized_provider:
                evidence_stmt = evidence_stmt.where(
                    RemediationRequest.provider == normalized_provider
                )
            evidence_rows = list((await self.db.execute(evidence_stmt)).all())
            for action, savings_sum in evidence_rows:
                key = str(getattr(action, "value", action)).lower()
                bucket = _ensure_bucket(key)
                bucket["realized_monthly_usd"] += _as_float(savings_sum)

            # Fallback: completed remediations without evidence -> use estimated_monthly_savings.
            fallback_stmt = (
                select(
                    RemediationRequest.action,
                    func.coalesce(
                        func.sum(RemediationRequest.estimated_monthly_savings), 0
                    ),
                )
                .outerjoin(
                    RealizedSavingsEvent,
                    (
                        RealizedSavingsEvent.remediation_request_id
                        == RemediationRequest.id
                    )
                    & (RealizedSavingsEvent.tenant_id == RemediationRequest.tenant_id),
                )
                .where(
                    RemediationRequest.tenant_id == tenant_id,
                    RemediationRequest.status == RemediationStatus.COMPLETED.value,
                    completed_at >= window_start,
                    completed_at <= window_end,
                    RealizedSavingsEvent.id.is_(None),
                )
                .group_by(RemediationRequest.action)
            )
            if normalized_provider:
                fallback_stmt = fallback_stmt.where(
                    RemediationRequest.provider == normalized_provider
                )
            fallback_rows = list((await self.db.execute(fallback_stmt)).all())
            for action, savings_sum in fallback_rows:
                key = str(getattr(action, "value", action)).lower()
                bucket = _ensure_bucket(key)
                bucket["realized_monthly_usd"] += _as_float(savings_sum)

            notes = [
                "Opportunity is a snapshot of pending/approved/scheduled remediations, grouped by action.",
                "Realized uses finance-grade ledger deltas where evidence exists; otherwise it falls back to estimated monthly savings.",
            ]

        # Order buckets by opportunity, then realized (desc), with stable key tie-break.
        bucket_items = sorted(
            buckets_by_key.items(),
            key=lambda item: (
                item[1]["opportunity_monthly_usd"],
                item[1]["realized_monthly_usd"],
                item[0],
            ),
            reverse=True,
        )
        truncated = len(bucket_items) > top_limit
        bucket_items = bucket_items[:top_limit]

        buckets = [
            SavingsProofDrilldownBucket(key=key, **values)
            for key, values in bucket_items
        ]
        opportunity_total = sum(item.opportunity_monthly_usd for item in buckets)
        realized_total = sum(item.realized_monthly_usd for item in buckets)

        if truncated:
            notes.append(f"Buckets truncated to top {top_limit} by opportunity.")

        payload = SavingsProofDrilldownResponse(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            as_of=now.isoformat(),
            tier=str(tier),
            provider=normalized_provider,
            dimension=dim,
            opportunity_monthly_usd=round(float(opportunity_total), 2),
            realized_monthly_usd=round(float(realized_total), 2),
            buckets=buckets,
            truncated=truncated,
            limit=top_limit,
            notes=notes,
        )

        logger.info(
            "savings_proof_drilldown_generated",
            tenant_id=str(tenant_id),
            provider=normalized_provider,
            dimension=dim,
            start_date=payload.start_date,
            end_date=payload.end_date,
            opportunity_monthly_usd=payload.opportunity_monthly_usd,
            realized_monthly_usd=payload.realized_monthly_usd,
            buckets=len(payload.buckets),
            truncated=payload.truncated,
        )

        return payload

    @staticmethod
    def render_csv(payload: SavingsProofResponse) -> str:
        lines: list[str] = []
        lines.append(
            "provider,opportunity_monthly_usd,realized_monthly_usd,open_recommendations,applied_recommendations,pending_remediations,completed_remediations"
        )
        for item in payload.breakdown:
            lines.append(
                f"{item.provider},{item.opportunity_monthly_usd:.2f},{item.realized_monthly_usd:.2f},"
                f"{item.open_recommendations},{item.applied_recommendations},"
                f"{item.pending_remediations},{item.completed_remediations}"
            )
        lines.append("")
        lines.append(
            f"TOTAL,{payload.opportunity_monthly_usd:.2f},{payload.realized_monthly_usd:.2f},"
            f"{payload.open_recommendations},{payload.applied_recommendations},"
            f"{payload.pending_remediations},{payload.completed_remediations}"
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def render_drilldown_csv(payload: SavingsProofDrilldownResponse) -> str:
        header = [
            payload.dimension,
            "opportunity_monthly_usd",
            "realized_monthly_usd",
            "open_recommendations",
            "applied_recommendations",
            "pending_remediations",
            "completed_remediations",
        ]
        lines = [",".join(header)]
        for item in payload.buckets:
            lines.append(
                ",".join(
                    [
                        str(item.key),
                        f"{item.opportunity_monthly_usd:.2f}",
                        f"{item.realized_monthly_usd:.2f}",
                        str(item.open_recommendations),
                        str(item.applied_recommendations),
                        str(item.pending_remediations),
                        str(item.completed_remediations),
                    ]
                )
            )
        lines.append("")
        lines.append(
            f"TOTAL,{payload.opportunity_monthly_usd:.2f},{payload.realized_monthly_usd:.2f},"
            f"{sum(b.open_recommendations for b in payload.buckets)},"
            f"{sum(b.applied_recommendations for b in payload.buckets)},"
            f"{sum(b.pending_remediations for b in payload.buckets)},"
            f"{sum(b.completed_remediations for b in payload.buckets)}"
        )
        return "\n".join(lines) + "\n"
