"""
Realized Savings (Finance-Grade) v1

Computes realized savings from the billing ledger using post-action deltas.

v1 scope:
- Remediation-driven actions only (RemediationRequest -> RealizedSavingsEvent)
- Requires a sufficiently specific slice:
  - connection_id (account scope) AND
  - resource_id (resource scope)
- Uses finalized ledger rows only (cost_status == FINAL) to avoid prelim noise.

This intentionally does not try to be "perfect finance" yet (invoice-linking, restatements, etc).
It provides a deterministic, explainable baseline for procurement evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CostRecord
from app.models.realized_savings import RealizedSavingsEvent
from app.models.remediation import RemediationRequest, RemediationStatus

logger = structlog.get_logger()


@dataclass(frozen=True)
class RealizedSavingsWindow:
    baseline_start: date
    baseline_end: date
    measurement_start: date
    measurement_end: date


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


class RealizedSavingsService:
    """
    Computes and persists realized savings evidence for remediation requests.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_windows(
        *,
        executed_day: date,
        baseline_days: int,
        measurement_days: int,
        gap_days: int = 1,
    ) -> RealizedSavingsWindow:
        if baseline_days <= 0 or measurement_days <= 0:
            raise ValueError("baseline_days and measurement_days must be > 0")
        if gap_days < 0:
            gap_days = 0

        baseline_end = executed_day - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=baseline_days - 1)

        measurement_start = executed_day + timedelta(days=gap_days)
        measurement_end = measurement_start + timedelta(days=measurement_days - 1)

        return RealizedSavingsWindow(
            baseline_start=baseline_start,
            baseline_end=baseline_end,
            measurement_start=measurement_start,
            measurement_end=measurement_end,
        )

    async def compute_for_request(
        self,
        *,
        tenant_id: UUID,
        request: RemediationRequest,
        baseline_days: int = 7,
        measurement_days: int = 7,
        gap_days: int = 1,
        monthly_multiplier_days: int = 30,
        require_final: bool = True,
    ) -> RealizedSavingsEvent | None:
        """
        Compute and upsert a RealizedSavingsEvent for a completed remediation request.

        Returns the upserted event or None if the request is not eligible (insufficient data / missing scope).
        """
        if request.tenant_id != tenant_id:
            raise ValueError("request does not belong to tenant")

        if request.status != RemediationStatus.COMPLETED:
            return None
        if request.executed_at is None:
            return None

        account_id = getattr(request, "connection_id", None)
        if account_id is None:
            # Without an account scope, the billing slice is too broad to be finance-grade.
            return None

        resource_id = str(getattr(request, "resource_id", "") or "").strip()
        if not resource_id:
            return None

        executed_at = request.executed_at
        executed_day = executed_at.date()

        windows = self._build_windows(
            executed_day=executed_day,
            baseline_days=baseline_days,
            measurement_days=measurement_days,
            gap_days=gap_days,
        )

        # Use yesterday as the safe "as of" boundary for finalized billing data.
        as_of_day = date.today() - timedelta(days=1)
        if windows.measurement_end > as_of_day:
            return None

        filters: list[Any] = [
            CostRecord.tenant_id == tenant_id,
            CostRecord.account_id == account_id,
            CostRecord.resource_id == resource_id,
        ]
        if require_final:
            filters.append(CostRecord.cost_status == "FINAL")

        baseline_total, baseline_days_observed = await self._window_cost(
            filters=filters,
            start_day=windows.baseline_start,
            end_day=windows.baseline_end,
        )
        measurement_total, measurement_days_observed = await self._window_cost(
            filters=filters,
            start_day=windows.measurement_start,
            end_day=windows.measurement_end,
        )

        if (
            baseline_days_observed < baseline_days
            or measurement_days_observed < measurement_days
        ):
            # Too incomplete to treat as finance-grade evidence.
            return None

        baseline_avg = (
            (baseline_total / Decimal(baseline_days_observed))
            if baseline_days_observed
            else Decimal("0")
        )
        measurement_avg = (
            (measurement_total / Decimal(measurement_days_observed))
            if measurement_days_observed
            else Decimal("0")
        )

        delta = baseline_avg - measurement_avg
        realized_daily = delta if delta > 0 else Decimal("0")
        realized_monthly = realized_daily * Decimal(str(monthly_multiplier_days))

        confidence = Decimal("0.90")
        if (
            baseline_days_observed < baseline_days
            or measurement_days_observed < measurement_days
        ):
            confidence = Decimal("0.60")

        details = {
            "executed_at": executed_at.isoformat(),
            "windows": {
                "baseline": {
                    "start": windows.baseline_start.isoformat(),
                    "end": windows.baseline_end.isoformat(),
                    "observed_days": baseline_days_observed,
                    "expected_days": baseline_days,
                    "total_cost_usd": str(baseline_total),
                },
                "measurement": {
                    "start": windows.measurement_start.isoformat(),
                    "end": windows.measurement_end.isoformat(),
                    "observed_days": measurement_days_observed,
                    "expected_days": measurement_days,
                    "total_cost_usd": str(measurement_total),
                },
            },
            "require_final": require_final,
            "clamped_at_zero": bool(delta <= 0),
        }

        now = datetime.now(timezone.utc)
        existing = await self.db.scalar(
            select(RealizedSavingsEvent).where(
                RealizedSavingsEvent.tenant_id == tenant_id,
                RealizedSavingsEvent.remediation_request_id == request.id,
            )
        )
        if existing is None:
            existing = RealizedSavingsEvent(
                tenant_id=tenant_id,
                remediation_request_id=request.id,
                provider=str(request.provider or "").strip().lower() or "unknown",
                account_id=account_id,
                resource_id=resource_id,
                service=None,
                region=str(getattr(request, "region", "") or None),
                method="ledger_delta_avg_daily_v1",
                baseline_start_date=windows.baseline_start,
                baseline_end_date=windows.baseline_end,
                measurement_start_date=windows.measurement_start,
                measurement_end_date=windows.measurement_end,
                baseline_total_cost_usd=baseline_total,
                baseline_observed_days=baseline_days_observed,
                measurement_total_cost_usd=measurement_total,
                measurement_observed_days=measurement_days_observed,
                baseline_avg_daily_cost_usd=baseline_avg,
                measurement_avg_daily_cost_usd=measurement_avg,
                realized_avg_daily_savings_usd=realized_daily,
                realized_monthly_savings_usd=realized_monthly,
                monthly_multiplier_days=int(monthly_multiplier_days),
                confidence_score=confidence,
                details=details,
                computed_at=now,
            )
            self.db.add(existing)
        else:
            existing.provider = (
                str(request.provider or "").strip().lower() or existing.provider
            )
            existing.account_id = account_id
            existing.resource_id = resource_id
            existing.region = str(getattr(request, "region", "") or None)
            existing.method = "ledger_delta_avg_daily_v1"
            existing.baseline_start_date = windows.baseline_start
            existing.baseline_end_date = windows.baseline_end
            existing.measurement_start_date = windows.measurement_start
            existing.measurement_end_date = windows.measurement_end
            existing.baseline_total_cost_usd = baseline_total
            existing.baseline_observed_days = baseline_days_observed
            existing.measurement_total_cost_usd = measurement_total
            existing.measurement_observed_days = measurement_days_observed
            existing.baseline_avg_daily_cost_usd = baseline_avg
            existing.measurement_avg_daily_cost_usd = measurement_avg
            existing.realized_avg_daily_savings_usd = realized_daily
            existing.realized_monthly_savings_usd = realized_monthly
            existing.monthly_multiplier_days = int(monthly_multiplier_days)
            existing.confidence_score = confidence
            existing.details = details
            existing.computed_at = now

        await self.db.flush()

        logger.info(
            "realized_savings_computed",
            tenant_id=str(tenant_id),
            remediation_request_id=str(request.id),
            account_id=str(account_id),
            resource_id=resource_id,
            baseline_avg_daily=float(baseline_avg),
            measurement_avg_daily=float(measurement_avg),
            realized_monthly=float(realized_monthly),
        )

        return existing

    async def _window_cost(
        self,
        *,
        filters: list[Any],
        start_day: date,
        end_day: date,
    ) -> tuple[Decimal, int]:
        stmt = (
            select(
                func.coalesce(func.sum(CostRecord.cost_usd), 0),
                func.count(func.distinct(CostRecord.recorded_at)),
            )
            .where(*filters)
            .where(CostRecord.recorded_at >= start_day)
            .where(CostRecord.recorded_at <= end_day)
        )
        total, observed_days = (await self.db.execute(stmt)).one()
        total_dec = _decimal(total)
        days_int = int(observed_days or 0)
        return total_dec, days_int
