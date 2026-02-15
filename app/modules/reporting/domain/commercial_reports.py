"""
Commercial Proof Reports (Domain)

Provides deterministic, procurement-friendly report templates that combine:
- Leadership KPIs (spend + carbon + top services)
- Savings proof (opportunity vs realized actions)

v1: Quarterly report templates (previous quarter by default).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.domain.leadership_kpis import (
    LeadershipKpiService,
    LeadershipKpisResponse,
)
from app.modules.reporting.domain.savings_proof import (
    SavingsProofResponse,
    SavingsProofService,
)
from app.shared.core.pricing import PricingTier, normalize_tier

logger = structlog.get_logger()


def _quarter_window(year: int, quarter: int) -> tuple[date, date]:
    if quarter not in {1, 2, 3, 4}:
        raise ValueError("quarter must be 1..4")
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    end_month = start_month + 2
    end_day = monthrange(year, end_month)[1]
    end = date(year, end_month, end_day)
    return start, end


def _quarter_for_date(value: date) -> tuple[int, int, date]:
    quarter = ((value.month - 1) // 3) + 1
    start_month = (quarter - 1) * 3 + 1
    start = date(value.year, start_month, 1)
    return value.year, quarter, start


def _previous_full_quarter(as_of: date) -> tuple[int, int, date, date]:
    year, quarter, current_start = _quarter_for_date(as_of)
    prev_anchor = current_start - timedelta(days=1)
    prev_year, prev_quarter, _ = _quarter_for_date(prev_anchor)
    start, end = _quarter_window(prev_year, prev_quarter)
    return prev_year, prev_quarter, start, end


class QuarterlyCommercialProofResponse(BaseModel):
    period: str  # current|previous|explicit
    year: int
    quarter: int
    start_date: str
    end_date: str
    as_of: str
    tier: str
    provider: str | None
    leadership_kpis: LeadershipKpisResponse
    savings_proof: SavingsProofResponse
    notes: list[str]


class CommercialProofReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def quarterly_report(
        self,
        *,
        tenant_id: UUID,
        tier: PricingTier | str,
        period: str = "previous",
        year: int | None = None,
        quarter: int | None = None,
        as_of: date | None = None,
        provider: Optional[str] = None,
    ) -> QuarterlyCommercialProofResponse:
        tier_enum = normalize_tier(tier)
        as_of_date = as_of or date.today()
        normalized_provider = provider.strip().lower() if provider else None

        if year is not None or quarter is not None:
            if year is None or quarter is None:
                raise ValueError("year and quarter must be provided together")
            q_start, q_end = _quarter_window(int(year), int(quarter))
            report_period = "explicit"
            report_year = int(year)
            report_quarter = int(quarter)
            window_start = q_start
            window_end = q_end
        else:
            normalized_period = str(period or "previous").strip().lower()
            if normalized_period not in {"current", "previous"}:
                raise ValueError("period must be 'current' or 'previous'")

            if normalized_period == "current":
                report_year, report_quarter, current_start = _quarter_for_date(
                    as_of_date
                )
                report_period = "current"
                window_start = current_start
                window_end = as_of_date
            else:
                report_year, report_quarter, window_start, window_end = (
                    _previous_full_quarter(as_of_date)
                )
                report_period = "previous"

        leadership = await LeadershipKpiService(self.db).compute(
            tenant_id=tenant_id,
            tier=tier_enum,
            start_date=window_start,
            end_date=window_end,
            provider=normalized_provider,
            include_preliminary=False,
            top_services_limit=10,
        )
        savings = await SavingsProofService(self.db).generate(
            tenant_id=tenant_id,
            tier=tier_enum.value,
            start_date=window_start,
            end_date=window_end,
            provider=normalized_provider,
        )

        payload = QuarterlyCommercialProofResponse(
            period=report_period,
            year=report_year,
            quarter=report_quarter,
            start_date=window_start.isoformat(),
            end_date=window_end.isoformat(),
            as_of=datetime.now(timezone.utc).isoformat(),
            tier=tier_enum.value,
            provider=normalized_provider,
            leadership_kpis=leadership,
            savings_proof=savings,
            notes=[
                "Leadership KPIs are ledger-backed aggregates over the report window (FINAL rows by default).",
                "Savings proof includes finance-grade realized savings evidence when present; otherwise it falls back to estimated savings metadata.",
            ],
        )

        logger.info(
            "commercial_quarterly_report_computed",
            tenant_id=str(tenant_id),
            year=payload.year,
            quarter=payload.quarter,
            period=payload.period,
            provider=normalized_provider,
            total_cost_usd=payload.leadership_kpis.total_cost_usd,
            realized_monthly_usd=payload.savings_proof.realized_monthly_usd,
        )
        return payload

    @staticmethod
    def render_quarterly_csv(payload: QuarterlyCommercialProofResponse) -> str:
        # Summary
        lines: list[str] = []
        lines.append(
            "year,quarter,period,start_date,end_date,total_cost_usd,carbon_total_kgco2e,carbon_coverage_percent,opportunity_monthly_usd,realized_monthly_usd"
        )
        lines.append(
            f"{payload.year},{payload.quarter},{payload.period},{payload.start_date},{payload.end_date},"
            f"{payload.leadership_kpis.total_cost_usd:.4f},{payload.leadership_kpis.carbon_total_kgco2e:.4f},"
            f"{payload.leadership_kpis.carbon_coverage_percent:.4f},{payload.savings_proof.opportunity_monthly_usd:.2f},"
            f"{payload.savings_proof.realized_monthly_usd:.2f}"
        )
        lines.append("")

        # Cost by provider (leadership KPI)
        lines.append("cost_by_provider:provider,cost_usd")
        for provider, cost in sorted(
            payload.leadership_kpis.cost_by_provider.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            lines.append(f"{provider},{cost:.4f}")
        lines.append("")

        # Savings proof breakdown
        lines.append(
            "savings_by_provider:provider,opportunity_monthly_usd,realized_monthly_usd,open_recommendations,applied_recommendations,pending_remediations,completed_remediations"
        )
        for item in payload.savings_proof.breakdown:
            lines.append(
                f"{item.provider},{item.opportunity_monthly_usd:.2f},{item.realized_monthly_usd:.2f},"
                f"{item.open_recommendations},{item.applied_recommendations},"
                f"{item.pending_remediations},{item.completed_remediations}"
            )
        lines.append("")

        # Top services (leadership KPI)
        lines.append("top_services:service,cost_usd")
        for svc in payload.leadership_kpis.top_services:
            lines.append(f"{svc.service},{svc.cost_usd:.4f}")
        return "\n".join(lines) + "\n"
