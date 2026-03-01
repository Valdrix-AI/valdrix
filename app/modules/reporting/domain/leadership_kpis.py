"""
Leadership KPI Export (Domain)

Provides an executive-friendly, deterministic summary of:
- Spend (total, provider breakdown, top services)
- Carbon (total + coverage)
- Savings proof (realized vs opportunity) when available for the tenant tier

This is designed for procurement and leadership reporting. It intentionally avoids
LLM-derived metrics and favors stable ledger-backed aggregates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CloudAccount, CostRecord
from app.models.enforcement import EnforcementDecision
from app.modules.reporting.domain.savings_proof import SavingsProofService
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    is_feature_enabled,
    normalize_tier,
)

logger = structlog.get_logger()


def _as_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


class LeadershipTopService(BaseModel):
    service: str
    cost_usd: float


class LeadershipKpisResponse(BaseModel):
    start_date: str
    end_date: str
    as_of: str
    tier: str
    provider: str | None
    include_preliminary: bool
    total_cost_usd: float
    cost_by_provider: dict[str, float]
    top_services: list[LeadershipTopService]
    carbon_total_kgco2e: float
    carbon_coverage_percent: float
    savings_opportunity_monthly_usd: float
    savings_realized_monthly_usd: float
    open_recommendations: int
    applied_recommendations: int
    pending_remediations: int
    completed_remediations: int
    security_high_risk_decisions: int = 0
    security_approval_required_decisions: int = 0
    security_anomaly_signal_decisions: int = 0
    notes: list[str]


class LeadershipKpiService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute(
        self,
        *,
        tenant_id: UUID,
        tier: PricingTier | str,
        start_date: date,
        end_date: date,
        provider: Optional[str] = None,
        include_preliminary: bool = False,
        top_services_limit: int = 10,
    ) -> LeadershipKpisResponse:
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        tier_enum = normalize_tier(tier)
        now = datetime.now(timezone.utc)

        normalized_provider = provider.strip().lower() if provider else None
        supported_providers = {
            "aws",
            "azure",
            "gcp",
            "saas",
            "license",
            "platform",
            "hybrid",
        }
        if normalized_provider and normalized_provider not in supported_providers:
            supported = ", ".join(sorted(supported_providers))
            raise ValueError(
                f"Unsupported provider '{provider}'. Use one of: {supported}"
            )

        top_limit = max(1, min(int(top_services_limit), 50))

        window_start = start_date
        window_end = end_date
        notes: list[str] = []

        base_filters: list[Any] = [
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= window_start,
            CostRecord.recorded_at <= window_end,
        ]
        if not include_preliminary:
            base_filters.append(CostRecord.cost_status == "FINAL")

        # Total spend + carbon totals/coverage.
        totals_stmt = (
            select(
                func.coalesce(func.sum(CostRecord.cost_usd), 0),
                func.count(CostRecord.id),
                func.count(CostRecord.carbon_kg),
                func.coalesce(func.sum(CostRecord.carbon_kg), 0),
            )
            .select_from(CostRecord)
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(*base_filters)
        )
        if normalized_provider:
            totals_stmt = totals_stmt.where(
                CloudAccount.provider == normalized_provider
            )
        totals_row = (await self.db.execute(totals_stmt)).first()
        total_cost_raw = totals_row[0] if totals_row else 0
        total_records = int(totals_row[1] or 0) if totals_row else 0
        carbon_records = int(totals_row[2] or 0) if totals_row else 0
        carbon_total_raw = totals_row[3] if totals_row else 0

        carbon_coverage = 0.0
        if total_records > 0:
            carbon_coverage = round((carbon_records / total_records) * 100.0, 4)
        if carbon_records == 0:
            notes.append(
                "Carbon coverage is 0%; carbon_kgco2e is unavailable for this window."
            )

        # Provider breakdown.
        provider_stmt = (
            select(
                CloudAccount.provider, func.coalesce(func.sum(CostRecord.cost_usd), 0)
            )
            .select_from(CostRecord)
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(*base_filters)
            .group_by(CloudAccount.provider)
        )
        if normalized_provider:
            provider_stmt = provider_stmt.where(
                CloudAccount.provider == normalized_provider
            )
        provider_rows = (await self.db.execute(provider_stmt)).all()
        cost_by_provider: dict[str, float] = {
            str(provider_name or "unknown").lower(): round(_as_float(total_cost), 4)
            for provider_name, total_cost in provider_rows
        }

        # Top services by spend.
        svc_stmt = (
            select(CostRecord.service, func.coalesce(func.sum(CostRecord.cost_usd), 0))
            .select_from(CostRecord)
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(*base_filters)
            .group_by(CostRecord.service)
            .order_by(func.sum(CostRecord.cost_usd).desc())
            .limit(top_limit)
        )
        if normalized_provider:
            svc_stmt = svc_stmt.where(CloudAccount.provider == normalized_provider)
        svc_rows = (await self.db.execute(svc_stmt)).all()
        top_services = [
            LeadershipTopService(
                service=str(service or "unknown"), cost_usd=round(_as_float(cost), 4)
            )
            for service, cost in svc_rows
        ]

        # Security posture indicators from deterministic enforcement decisions.
        security_stmt = select(
            func.count()
            .filter(EnforcementDecision.risk_class.in_(("high", "critical")))
            .label("high_risk_count"),
            func.count()
            .filter(EnforcementDecision.approval_required.is_(True))
            .label("approval_required_count"),
            func.count()
            .filter(EnforcementDecision.anomaly_signal.is_(True))
            .label("anomaly_signal_count"),
        ).where(
            EnforcementDecision.tenant_id == tenant_id,
            EnforcementDecision.created_at >= window_start,
            EnforcementDecision.created_at <= window_end,
        )
        security_row = (await self.db.execute(security_stmt)).first()
        security_high_risk_decisions = (
            int(security_row[0] or 0) if security_row else 0
        )
        security_approval_required_decisions = (
            int(security_row[1] or 0) if security_row else 0
        )
        security_anomaly_signal_decisions = (
            int(security_row[2] or 0) if security_row else 0
        )

        # Savings proof (tier-gated).
        savings_opportunity = 0.0
        savings_realized = 0.0
        open_recs = applied_recs = pending_rems = completed_rems = 0

        if is_feature_enabled(tier_enum, FeatureFlag.SAVINGS_PROOF):
            try:
                proof = await SavingsProofService(self.db).generate(
                    tenant_id=tenant_id,
                    tier=tier_enum.value,
                    start_date=window_start,
                    end_date=window_end,
                    provider=normalized_provider,
                )
                savings_opportunity = float(proof.opportunity_monthly_usd)
                savings_realized = float(proof.realized_monthly_usd)
                open_recs = int(proof.open_recommendations)
                applied_recs = int(proof.applied_recommendations)
                pending_rems = int(proof.pending_remediations)
                completed_rems = int(proof.completed_remediations)
            except Exception as exc:  # noqa: BLE001 - leadership export should degrade gracefully
                notes.append(f"Savings proof unavailable: {exc}")
        else:
            notes.append("Savings proof is not enabled for this tier.")

        payload = LeadershipKpisResponse(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            as_of=now.isoformat(),
            tier=tier_enum.value,
            provider=normalized_provider,
            include_preliminary=bool(include_preliminary),
            total_cost_usd=round(_as_float(total_cost_raw), 4),
            cost_by_provider=cost_by_provider,
            top_services=top_services,
            carbon_total_kgco2e=round(_as_float(carbon_total_raw), 4),
            carbon_coverage_percent=carbon_coverage,
            savings_opportunity_monthly_usd=round(float(savings_opportunity), 2),
            savings_realized_monthly_usd=round(float(savings_realized), 2),
            open_recommendations=open_recs,
            applied_recommendations=applied_recs,
            pending_remediations=pending_rems,
            completed_remediations=completed_rems,
            security_high_risk_decisions=security_high_risk_decisions,
            security_approval_required_decisions=security_approval_required_decisions,
            security_anomaly_signal_decisions=security_anomaly_signal_decisions,
            notes=notes,
        )

        logger.info(
            "leadership_kpis_computed",
            tenant_id=str(tenant_id),
            provider=normalized_provider,
            start_date=payload.start_date,
            end_date=payload.end_date,
            total_cost_usd=payload.total_cost_usd,
            savings_realized_monthly_usd=payload.savings_realized_monthly_usd,
            security_high_risk_decisions=payload.security_high_risk_decisions,
            security_approval_required_decisions=payload.security_approval_required_decisions,
            security_anomaly_signal_decisions=payload.security_anomaly_signal_decisions,
        )
        return payload

    @staticmethod
    def render_csv(payload: LeadershipKpisResponse) -> str:
        # Summary section.
        lines: list[str] = []
        lines.append(
            "start_date,end_date,total_cost_usd,carbon_total_kgco2e,carbon_coverage_percent,savings_opportunity_monthly_usd,savings_realized_monthly_usd,security_high_risk_decisions,security_approval_required_decisions,security_anomaly_signal_decisions"
        )
        lines.append(
            f"{payload.start_date},{payload.end_date},{payload.total_cost_usd:.4f},"
            f"{payload.carbon_total_kgco2e:.4f},{payload.carbon_coverage_percent:.4f},"
            f"{payload.savings_opportunity_monthly_usd:.2f},{payload.savings_realized_monthly_usd:.2f},"
            f"{payload.security_high_risk_decisions},{payload.security_approval_required_decisions},"
            f"{payload.security_anomaly_signal_decisions}"
        )
        lines.append("")

        # Provider breakdown.
        lines.append("provider,cost_usd")
        for provider, cost in sorted(
            payload.cost_by_provider.items(), key=lambda item: item[1], reverse=True
        ):
            lines.append(f"{provider},{cost:.4f}")
        lines.append("")

        # Top services.
        lines.append("service,cost_usd")
        for item in payload.top_services:
            lines.append(f"{item.service},{item.cost_usd:.4f}")
        return "\n".join(lines) + "\n"
