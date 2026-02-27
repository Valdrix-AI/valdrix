from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

import app.modules.enforcement.domain.reconciliation_worker as worker_module
from app.modules.enforcement.domain.reconciliation_worker import (
    EnforcementReconciliationSweepResult,
    EnforcementReconciliationWorker,
    _as_decimal,
    _as_int,
)


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeCounter":
        self._labels = dict(labels)
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append((dict(self._labels), float(amount)))


@pytest.mark.asyncio
async def test_reconciliation_worker_sends_sla_release_alert(monkeypatch) -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    service = AsyncMock()
    service.reconcile_overdue_reservations.return_value = SimpleNamespace(
        released_count=2,
        total_released_usd=Decimal("120.0000"),
        older_than_seconds=3600,
        decision_ids=[uuid4(), uuid4()],
    )
    service.list_reconciliation_exceptions.return_value = []

    send_alert = AsyncMock()
    sweep_metric = _FakeCounter()
    alerts_metric = _FakeCounter()

    monkeypatch.setattr(worker_module, "EnforcementService", lambda _db: service)
    monkeypatch.setattr(worker_module.NotificationDispatcher, "send_alert", send_alert)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL", sweep_metric)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL", alerts_metric)
    monkeypatch.setattr(
        worker_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=86400,
            ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES=500,
            ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT=200,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD=100.0,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT=5,
        ),
    )

    result = await EnforcementReconciliationWorker(db).run_for_tenant(tenant_id)

    assert result.released_count == 2
    assert result.total_released_usd == Decimal("120.0000")
    assert result.alerts_sent == ["sla_release"]
    send_alert.assert_awaited_once()
    assert ({"status": "success"}, 1.0) in sweep_metric.calls
    assert (
        {"alert_type": "sla_release", "severity": "warning"},
        1.0,
    ) in alerts_metric.calls


@pytest.mark.asyncio
async def test_reconciliation_worker_sends_drift_exception_alert(monkeypatch) -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    service = AsyncMock()
    service.reconcile_overdue_reservations.return_value = SimpleNamespace(
        released_count=0,
        total_released_usd=Decimal("0.0000"),
        older_than_seconds=3600,
        decision_ids=[],
    )
    exceptions = [
        SimpleNamespace(decision=SimpleNamespace(id=uuid4()), drift_usd=Decimal("80.0000")),
        SimpleNamespace(decision=SimpleNamespace(id=uuid4()), drift_usd=Decimal("60.0000")),
    ]
    service.list_reconciliation_exceptions.return_value = exceptions

    send_alert = AsyncMock()
    sweep_metric = _FakeCounter()
    alerts_metric = _FakeCounter()

    monkeypatch.setattr(worker_module, "EnforcementService", lambda _db: service)
    monkeypatch.setattr(worker_module.NotificationDispatcher, "send_alert", send_alert)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL", sweep_metric)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL", alerts_metric)
    monkeypatch.setattr(
        worker_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=86400,
            ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES=500,
            ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT=200,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD=100.0,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT=2,
        ),
    )

    result = await EnforcementReconciliationWorker(db).run_for_tenant(tenant_id)

    assert result.exceptions_count == 2
    assert result.total_abs_drift_usd == Decimal("140.0000")
    assert result.alerts_sent == ["drift_exception"]
    send_alert.assert_awaited_once()
    # 140 >= 100 and 2 exceptions at threshold -> warning severity path
    assert (
        {"alert_type": "drift_exception", "severity": "warning"},
        1.0,
    ) in alerts_metric.calls
    assert ({"status": "success"}, 1.0) in sweep_metric.calls


@pytest.mark.asyncio
async def test_reconciliation_worker_records_failure_metric(monkeypatch) -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    service = AsyncMock()
    service.reconcile_overdue_reservations.side_effect = RuntimeError("db failure")

    sweep_metric = _FakeCounter()

    monkeypatch.setattr(worker_module, "EnforcementService", lambda _db: service)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL", sweep_metric)
    monkeypatch.setattr(
        worker_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=86400,
            ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES=500,
            ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT=200,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD=100.0,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT=5,
        ),
    )

    with pytest.raises(RuntimeError, match="db failure"):
        await EnforcementReconciliationWorker(db).run_for_tenant(tenant_id)

    assert ({"status": "failure"}, 1.0) in sweep_metric.calls


def test_reconciliation_worker_helper_parsers_and_payload_branches() -> None:
    assert _as_decimal("invalid", Decimal("7.5")) == Decimal("7.5")
    assert _as_int("invalid", 42) == 42

    result = EnforcementReconciliationSweepResult(
        tenant_id=uuid4(),
        released_count=1,
        total_released_usd=Decimal("5"),
        older_than_seconds=3600,
        exceptions_count=2,
        overage_count=1,
        savings_count=1,
        total_abs_drift_usd=Decimal("3"),
        alerts_sent=["sla_release"],
    )
    payload = result.to_payload()
    assert payload["status"] == "completed"
    assert payload["released_count"] == 1


@pytest.mark.asyncio
async def test_reconciliation_worker_alert_send_failures_are_non_fatal(monkeypatch) -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    service = AsyncMock()
    service.reconcile_overdue_reservations.return_value = SimpleNamespace(
        released_count=1,
        total_released_usd=Decimal("5.0000"),
        older_than_seconds=3600,
        decision_ids=[uuid4()],
    )
    service.list_reconciliation_exceptions.return_value = [
        SimpleNamespace(decision=SimpleNamespace(id=uuid4()), drift_usd=Decimal("250.0000"))
    ]

    send_alert = AsyncMock(side_effect=RuntimeError("notify down"))
    sweep_metric = _FakeCounter()

    monkeypatch.setattr(worker_module, "EnforcementService", lambda _db: service)
    monkeypatch.setattr(worker_module.NotificationDispatcher, "send_alert", send_alert)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_SWEEP_RUNS_TOTAL", sweep_metric)
    monkeypatch.setattr(worker_module, "ENFORCEMENT_RECONCILIATION_ALERTS_TOTAL", _FakeCounter())
    monkeypatch.setattr(
        worker_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=86400,
            ENFORCEMENT_RECONCILIATION_SWEEP_MAX_RELEASES=500,
            ENFORCEMENT_RECONCILIATION_EXCEPTION_SCAN_LIMIT=200,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_THRESHOLD_USD=100.0,
            ENFORCEMENT_RECONCILIATION_DRIFT_ALERT_EXCEPTION_COUNT=1,
        ),
    )
    logger_warning = Mock()
    monkeypatch.setattr(worker_module.logger, "warning", logger_warning)

    result = await EnforcementReconciliationWorker(db).run_for_tenant(tenant_id)

    assert result.released_count == 1
    assert result.exceptions_count == 1
    # Both alert attempts fail, but worker still succeeds and records warning logs.
    assert logger_warning.call_count >= 2
    assert ({"status": "success"}, 1.0) in sweep_metric.calls
