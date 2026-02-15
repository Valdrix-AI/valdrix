"""
Deterministic Cost Anomaly Detection

Detect daily cost deltas per service/account with a rolling baseline and weekday seasonality.

Outputs: service, account, probable-cause classification, confidence score, severity.

This module is intentionally deterministic and does not depend on any LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.models.cloud import CloudAccount, CostRecord
from app.shared.core.cache import CacheService
from app.shared.core.notifications import NotificationDispatcher

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class DailyServiceCostRow:
    day: date
    provider: str
    account_id: UUID
    account_name: str | None
    service: str
    cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class CostAnomaly:
    day: date
    provider: str
    account_id: UUID
    account_name: str | None
    service: str
    actual_cost_usd: Decimal
    expected_cost_usd: Decimal
    delta_cost_usd: Decimal
    percent_change: float | None
    kind: str  # new_spend | spike | drop
    probable_cause: str
    confidence: float  # 0..1
    severity: str  # low | medium | high | critical


_SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def severity_gte(severity: str, minimum: str) -> bool:
    """Compare severities with a stable ordering."""
    return _SEVERITY_RANK.get(severity, 0) >= _SEVERITY_RANK.get(minimum, 0)


def detect_daily_cost_anomalies(
    rows: list[DailyServiceCostRow],
    *,
    target_date: date,
    lookback_days: int = 28,
    min_abs_usd: Decimal = Decimal("25"),
    min_percent: float = 30.0,
    min_weekday_samples: int = 2,
    min_active_days: int = 3,
) -> list[CostAnomaly]:
    """
    Detect anomalies for a single target_date.

    Design notes:
    - Uses weekday median baseline to capture weekly seasonality.
    - Fills missing days with zeros to avoid false anomalies for sporadic services.
    - Flags:
      - new_spend: expected == 0 and actual >= min_abs_usd
      - spike: positive delta exceeds thresholds
      - drop: negative delta exceeds thresholds
    """
    if lookback_days < 7:
        raise ValueError("lookback_days must be >= 7")
    if min_percent <= 0:
        raise ValueError("min_percent must be > 0")

    baseline_start = target_date - timedelta(days=lookback_days)
    baseline_end = target_date - timedelta(days=1)

    # key -> date -> cost
    series: dict[tuple[str, UUID, str], dict[date, Decimal]] = {}
    meta: dict[tuple[str, UUID, str], tuple[str | None]] = {}

    for r in rows:
        if r.day < baseline_start or r.day > target_date:
            continue
        provider = (r.provider or "").strip().lower() or "unknown"
        key = (provider, r.account_id, (r.service or "Unknown").strip() or "Unknown")
        series.setdefault(key, {})[r.day] = Decimal(r.cost_usd or 0)
        # Store name for output (single value per account)
        meta.setdefault(key, (r.account_name,))

    # Also consider keys that appear only on the target day
    # (handled already by series if present in rows for target_date).

    baseline_days: list[date] = []
    d = baseline_start
    while d <= baseline_end:
        baseline_days.append(d)
        d += timedelta(days=1)

    anomalies: list[CostAnomaly] = []

    for (provider, account_id, service), by_day in series.items():
        account_name = meta.get((provider, account_id, service), (None,))[0]

        # Build baseline values with explicit zeros for missing days.
        baseline_values = [Decimal(by_day.get(day, 0)) for day in baseline_days]
        active_days = sum(1 for v in baseline_values if v > 0)

        # If the service barely shows up in the lookback window, avoid "drop" spam.
        # We still allow "new_spend" based on expected==0.
        weekday_values = [
            Decimal(by_day.get(day, 0))
            for day in baseline_days
            if day.weekday() == target_date.weekday()
        ]
        all_values = baseline_values

        if len(weekday_values) >= min_weekday_samples:
            expected = median(weekday_values)
        else:
            expected = median(all_values) if all_values else Decimal("0")

        actual = Decimal(by_day.get(target_date, 0))
        delta = actual - expected

        percent_change: float | None
        if expected > 0:
            percent_change = float((delta / expected) * Decimal("100"))
        else:
            percent_change = None

        delta_abs = abs(delta)
        percent_abs = abs(percent_change) if percent_change is not None else 0.0

        kind: str | None = None
        probable_cause: str | None = None

        if expected == 0:
            if actual >= min_abs_usd:
                kind = "new_spend"
                probable_cause = "new_service_spend"
        else:
            if (
                delta >= min_abs_usd
                and percent_change is not None
                and percent_change >= min_percent
            ):
                kind = "spike"
                probable_cause = "spend_spike"
            elif (
                delta <= -min_abs_usd
                and percent_change is not None
                and percent_change <= -min_percent
                and active_days >= min_active_days
            ):
                kind = "drop"
                probable_cause = "spend_drop"

        if not kind or not probable_cause:
            continue

        severity = _classify_severity(delta_abs=delta_abs, percent_abs=percent_abs)
        confidence = _confidence(
            kind=kind,
            active_days=active_days,
            lookback_days=lookback_days,
            percent_abs=percent_abs,
            min_percent=min_percent,
        )

        anomalies.append(
            CostAnomaly(
                day=target_date,
                provider=provider,
                account_id=account_id,
                account_name=account_name,
                service=service,
                actual_cost_usd=actual,
                expected_cost_usd=expected,
                delta_cost_usd=delta,
                percent_change=None
                if percent_change is None
                else round(percent_change, 2),
                kind=kind,
                probable_cause=probable_cause,
                confidence=confidence,
                severity=severity,
            )
        )

    # Deterministic ordering: highest severity first, then largest delta.
    anomalies.sort(
        key=lambda a: (_SEVERITY_RANK.get(a.severity, 0), abs(a.delta_cost_usd)),
        reverse=True,
    )
    return anomalies


def _classify_severity(*, delta_abs: Decimal, percent_abs: float) -> str:
    # These thresholds are intentionally simple and deterministic.
    if delta_abs >= Decimal("1000") or percent_abs >= 500:
        return "critical"
    if delta_abs >= Decimal("250") or percent_abs >= 200:
        return "high"
    if delta_abs >= Decimal("100") or percent_abs >= 100:
        return "medium"
    return "low"


def _confidence(
    *,
    kind: str,
    active_days: int,
    lookback_days: int,
    percent_abs: float,
    min_percent: float,
) -> float:
    # Confidence reflects: signal strength (how far past threshold) and baseline depth.
    if kind == "new_spend":
        return 0.9 if lookback_days >= 14 else 0.7

    baseline_factor = min(1.0, active_days / 7.0) if active_days > 0 else 0.2
    strength = percent_abs / max(min_percent, 1.0)
    strength_factor = min(1.0, strength / 2.0)  # threshold => ~0.5, 2x => 1.0

    score = max(0.1, min(1.0, baseline_factor * strength_factor))
    return round(score, 2)


class CostAnomalyDetectionService:
    """DB-backed deterministic anomaly detection service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def fetch_daily_service_costs(
        self,
        *,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: str | None = None,
    ) -> list[DailyServiceCostRow]:
        """
        Aggregate cost records into daily provider/account/service totals.
        """
        stmt = (
            select(
                CostRecord.recorded_at.label("day"),
                CloudAccount.provider.label("provider"),
                CloudAccount.id.label("account_id"),
                CloudAccount.name.label("account_name"),
                CostRecord.service.label("service"),
                func.coalesce(func.sum(CostRecord.cost_usd), 0).label("cost_usd"),
            )
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
            )
            .group_by(
                CostRecord.recorded_at,
                CloudAccount.provider,
                CloudAccount.id,
                CloudAccount.name,
                CostRecord.service,
            )
        )
        if provider:
            stmt = stmt.where(CloudAccount.provider == provider.strip().lower())

        result = await self.db.execute(stmt)
        rows: list[DailyServiceCostRow] = []
        for r in result.all():
            rows.append(
                DailyServiceCostRow(
                    day=r.day,
                    provider=str(r.provider or "unknown"),
                    account_id=r.account_id,
                    account_name=str(r.account_name)
                    if r.account_name is not None
                    else None,
                    service=str(r.service or "Unknown"),
                    cost_usd=Decimal(r.cost_usd or 0),
                )
            )
        return rows

    async def detect(
        self,
        *,
        tenant_id: UUID,
        target_date: date,
        provider: str | None = None,
        lookback_days: int = 28,
        min_abs_usd: Decimal = Decimal("25"),
        min_percent: float = 30.0,
        min_severity: str = "medium",
    ) -> list[CostAnomaly]:
        start_date = target_date - timedelta(days=lookback_days)
        rows = await self.fetch_daily_service_costs(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=target_date,
            provider=provider,
        )
        anomalies = detect_daily_cost_anomalies(
            rows,
            target_date=target_date,
            lookback_days=lookback_days,
            min_abs_usd=min_abs_usd,
            min_percent=min_percent,
        )
        return [item for item in anomalies if severity_gte(item.severity, min_severity)]


async def dispatch_cost_anomaly_alerts(
    *,
    tenant_id: UUID,
    anomalies: list[CostAnomaly],
    suppression_hours: int = 24,
    db: AsyncSession | None = None,
) -> int:
    """
    Dispatch anomaly alerts with per-anomaly suppression windows.
    """
    if suppression_hours < 1:
        suppression_hours = 1

    cache = CacheService()
    jira = None
    jira_allowed = False
    if db is not None:
        try:
            from app.shared.core.pricing import (
                FeatureFlag,
                get_tenant_tier,
                is_feature_enabled,
            )
            from app.modules.notifications.domain import get_tenant_jira_service

            tier = await get_tenant_tier(tenant_id, db)
            jira_allowed = is_feature_enabled(tier, FeatureFlag.INCIDENT_INTEGRATIONS)
            if jira_allowed:
                jira = await get_tenant_jira_service(db, tenant_id)
        except Exception:
            jira_allowed = False
            jira = None
    alerted = 0
    for item in anomalies:
        fingerprint = (
            # One alert per anomaly per day (prevents cross-day suppression).
            f"anomaly:{tenant_id}:{item.day.isoformat()}:{item.provider}:{item.account_id}:"
            f"{item.service}:{item.kind}"
        )
        if await cache.get(fingerprint):
            continue
        try:
            await NotificationDispatcher.send_alert(
                title=f"Cost anomaly ({item.severity}) - {item.service}",
                message=(
                    f"Tenant: {tenant_id}\n"
                    f"Date: {item.day.isoformat()}\n"
                    f"Provider: {item.provider}\n"
                    f"Account: {item.account_name or item.account_id}\n"
                    f"Service: {item.service}\n"
                    f"Type: {item.kind}\n"
                    f"Actual: ${float(item.actual_cost_usd):,.2f}\n"
                    f"Expected: ${float(item.expected_cost_usd):,.2f}\n"
                    f"Delta: ${float(item.delta_cost_usd):,.2f}\n"
                    f"Confidence: {item.confidence:.2f}\n"
                    f"Cause: {item.probable_cause}"
                ),
                severity="critical"
                if item.severity in {"high", "critical"}
                else "warning",
                tenant_id=str(tenant_id),
                db=db,
            )

            # Also emit a workflow event when tenant-scoped dispatchers are configured.
            # This keeps "actionability" consistent with remediation/policy integrations.
            try:
                await NotificationDispatcher._dispatch_workflow_event(  # noqa: SLF001
                    event_type="cost.anomaly_detected",
                    payload={
                        "tenant_id": str(tenant_id),
                        "day": item.day.isoformat(),
                        "provider": item.provider,
                        "account_id": str(item.account_id),
                        "account_name": item.account_name,
                        "service": item.service,
                        "kind": item.kind,
                        "severity": item.severity,
                        "actual_cost_usd": float(item.actual_cost_usd),
                        "expected_cost_usd": float(item.expected_cost_usd),
                        "delta_cost_usd": float(item.delta_cost_usd),
                        "percent_change": item.percent_change,
                        "confidence": item.confidence,
                        "probable_cause": item.probable_cause,
                    },
                    db=db,
                    tenant_id=str(tenant_id),
                )
            except Exception as e:
                # Keep anomaly notifications best-effort; workflow automation can be optional per tenant.
                logger.debug(
                    "anomaly_workflow_dispatch_failed", error=str(e), exc_info=True
                )

            if (
                jira_allowed
                and jira is not None
                and item.severity in {"high", "critical"}
            ):
                try:
                    await jira.create_cost_anomaly_issue(
                        tenant_id=str(tenant_id),
                        day=item.day.isoformat(),
                        provider=item.provider,
                        account_id=str(item.account_id),
                        account_name=item.account_name,
                        service=item.service,
                        kind=item.kind,
                        severity=item.severity,
                        actual_cost_usd=float(item.actual_cost_usd),
                        expected_cost_usd=float(item.expected_cost_usd),
                        delta_cost_usd=float(item.delta_cost_usd),
                        percent_change=item.percent_change,
                        confidence=float(item.confidence),
                        probable_cause=item.probable_cause,
                    )
                except Exception as e:
                    logger.debug(
                        "anomaly_jira_issue_failed", error=str(e), exc_info=True
                    )
            await cache.set(
                fingerprint,
                {"ts": datetime.now(timezone.utc).isoformat()},
                ttl=timedelta(hours=suppression_hours),
            )
            alerted += 1
        except Exception as e:
            # Keep dispatch best-effort; callers can handle global failure metrics.
            logger.debug("anomaly_dispatch_item_failed", error=str(e), exc_info=True)
            continue
    return alerted
