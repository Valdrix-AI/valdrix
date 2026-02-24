from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.config import get_settings
from app.shared.core.notifications import NotificationDispatcher
from app.shared.core.ops_metrics import (
    ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL,
    ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL,
)

logger = structlog.get_logger()

_SYSTEM_ACTOR_ID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(frozen=True)
class EnforcementReconciliationSweepResult:
    tenant_id: UUID
    released_count: int
    total_released_usd: Decimal
    older_than_seconds: int
    exceptions_count: int
    overage_count: int
    savings_count: int
    total_abs_drift_usd: Decimal
    alerts_sent: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "tenant_id": str(self.tenant_id),
            "released_count": int(self.released_count),
            "total_released_usd": str(self.total_released_usd),
            "older_than_seconds": int(self.older_than_seconds),
            "exceptions_count": int(self.exceptions_count),
            "overage_count": int(self.overage_count),
            "savings_count": int(self.savings_count),
            "total_abs_drift_usd": str(self.total_abs_drift_usd),
            "alerts_sent": list(self.alerts_sent),
        }


def _as_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


class EnforcementReconciliationWorker:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _settings(self) -> SimpleNamespace:
        raw = get_settings()
        return SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=max(
                60,
                min(
                    _as_int(
                        getattr(
                            raw,
                            "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS",
                            86400,
                        ),
                        86400,
                    ),
                    604800,
                ),
            ),
            ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES=max(
                1,
                min(
                    _as_int(
                        getattr(raw, "ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES", 500),
                        500,
                    ),
                    1000,
                ),
            ),
            ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT=max(
                1,
                min(
                    _as_int(
                        getattr(
                            raw,
                            "ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT",
                            200,
                        ),
                        200,
                    ),
                    1000,
                ),
            ),
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD=max(
                Decimal("0"),
                _as_decimal(
                    getattr(
                        raw,
                        "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD",
                        100.0,
                    ),
                    Decimal("100.0"),
                ),
            ),
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT=max(
                1,
                _as_int(
                    getattr(
                        raw,
                        "ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT",
                        5,
                    ),
                    5,
                ),
            ),
        )

    async def run_for_tenant(self, tenant_id: UUID) -> EnforcementReconciliationSweepResult:
        settings = self._settings()
        service = EnforcementService(self.db)

        try:
            overdue_summary = await service.reconcile_overdue_reservations(
                tenant_id=tenant_id,
                actor_id=_SYSTEM_ACTOR_ID,
                older_than_seconds=settings.ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS,
                limit=settings.ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES,
            )
            exceptions = await service.list_reconciliation_exceptions(
                tenant_id=tenant_id,
                limit=settings.ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT,
            )

            overage_count = sum(
                1 for item in exceptions if item.drift_usd > Decimal("0")
            )
            savings_count = sum(
                1 for item in exceptions if item.drift_usd < Decimal("0")
            )
            total_abs_drift = sum(
                (abs(item.drift_usd) for item in exceptions),
                Decimal("0.0000"),
            )

            alerts_sent: list[str] = []
            if overdue_summary.released_count > 0:
                await self._send_sla_release_alert(
                    tenant_id=tenant_id,
                    released_count=overdue_summary.released_count,
                    total_released_usd=overdue_summary.total_released_usd,
                    older_than_seconds=overdue_summary.older_than_seconds,
                )
                alerts_sent.append("sla_release")

            if (
                total_abs_drift
                >= settings.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD
                or len(exceptions)
                >= settings.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT
            ):
                await self._send_drift_exception_alert(
                    tenant_id=tenant_id,
                    exceptions=exceptions,
                    total_abs_drift_usd=total_abs_drift,
                    threshold_usd=settings.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD,
                    threshold_count=settings.ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT,
                )
                alerts_sent.append("drift_exception")

            ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL.labels(status="success").inc()
            return EnforcementReconciliationSweepResult(
                tenant_id=tenant_id,
                released_count=overdue_summary.released_count,
                total_released_usd=overdue_summary.total_released_usd,
                older_than_seconds=overdue_summary.older_than_seconds,
                exceptions_count=len(exceptions),
                overage_count=overage_count,
                savings_count=savings_count,
                total_abs_drift_usd=total_abs_drift,
                alerts_sent=alerts_sent,
            )
        except Exception:
            ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL.labels(status="failure").inc()
            raise

    async def _send_sla_release_alert(
        self,
        *,
        tenant_id: UUID,
        released_count: int,
        total_released_usd: Decimal,
        older_than_seconds: int,
    ) -> None:
        try:
            await NotificationDispatcher.send_alert(
                title="Enforcement SLA Reconciliation Released Stale Reservations",
                message=(
                    f"Released {released_count} stale reservation(s) totaling "
                    f"${total_released_usd} after SLA {older_than_seconds}s."
                ),
                severity="warning",
                tenant_id=str(tenant_id),
                db=self.db,
            )
            ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL.labels(
                alert_type="sla_release",
                severity="warning",
            ).inc()
        except Exception as exc:  # noqa: BLE001 - best effort alerting
            logger.warning(
                "enforcement_reconciliation_sla_alert_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )

    async def _send_drift_exception_alert(
        self,
        *,
        tenant_id: UUID,
        exceptions: list[Any],
        total_abs_drift_usd: Decimal,
        threshold_usd: Decimal,
        threshold_count: int,
    ) -> None:
        severe = (
            total_abs_drift_usd >= (threshold_usd * Decimal("3"))
            or len(exceptions) >= (threshold_count * 2)
        )
        severity = "error" if severe else "warning"
        top_entries = ", ".join(
            f"{item.decision.id}:{item.drift_usd}" for item in exceptions[:5]
        )
        try:
            await NotificationDispatcher.send_alert(
                title="Enforcement Reconciliation Drift Exceptions Detected",
                message=(
                    f"{len(exceptions)} drift exception(s), total absolute drift "
                    f"${total_abs_drift_usd}. Thresholds: "
                    f"${threshold_usd} or {threshold_count} exceptions. "
                    f"Top: {top_entries or 'none'}"
                ),
                severity=severity,
                tenant_id=str(tenant_id),
                db=self.db,
            )
            ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL.labels(
                alert_type="drift_exception",
                severity=severity,
            ).inc()
        except Exception as exc:  # noqa: BLE001 - best effort alerting
            logger.warning(
                "enforcement_reconciliation_drift_alert_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
