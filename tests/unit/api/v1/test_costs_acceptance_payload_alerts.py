from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.reporting.api.v1 import costs as costs_api
from tests.unit.api.v1.costs_acceptance_test_helpers import FakeDB, standard_unit_settings, user


@pytest.mark.asyncio
async def test_canonical_quality_alert_failure_branch_records_error() -> None:
    db = FakeDB()
    quality = {
        "target_percentage": 99.0,
        "total_records": 100,
        "mapped_percentage": 85.0,
        "unmapped_records": 15,
        "meets_target": False,
        "status": "warning",
    }

    with (
        patch.object(
            costs_api.CostAggregator,
            "get_canonical_data_quality",
            new=AsyncMock(return_value=quality),
        ),
        patch.object(
            costs_api.NotificationDispatcher,
            "send_alert",
            new=AsyncMock(side_effect=RuntimeError("notify-failed")),
        ),
    ):
        out = await costs_api.get_canonical_quality(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            notify_on_breach=True,
            db=db,  # type: ignore[arg-type]
            current_user=user(),
        )

    assert out["alert_triggered"] is False
    assert out["alert_error"] == "notify-failed"


@pytest.mark.asyncio
async def test_get_canonical_quality_skips_alert_when_notify_flag_disabled() -> None:
    db = FakeDB()
    quality = {
        "target_percentage": 99.0,
        "total_records": 250,
        "mapped_percentage": 80.0,
        "unmapped_records": 50,
        "meets_target": False,
    }

    with (
        patch.object(
            costs_api.CostAggregator,
            "get_canonical_data_quality",
            new=AsyncMock(return_value=quality),
        ),
        patch.object(
            costs_api.NotificationDispatcher,
            "send_alert",
            new=AsyncMock(),
        ) as mock_alert,
    ):
        out = await costs_api.get_canonical_quality(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            notify_on_breach=False,
            db=db,  # type: ignore[arg-type]
            current_user=user(),
        )

    assert out == quality
    mock_alert.assert_not_awaited()
    assert "alert_triggered" not in out


@pytest.mark.asyncio
async def test_get_cost_anomalies_skips_dispatch_when_alert_disabled() -> None:
    db = FakeDB()
    anomaly = SimpleNamespace()
    service = SimpleNamespace(detect=AsyncMock(return_value=[anomaly]))

    with (
        patch.object(costs_api, "CostAnomalyDetectionService", return_value=service),
        patch.object(
            costs_api,
            "dispatch_cost_anomaly_alerts",
            new=AsyncMock(return_value=1),
        ) as mock_dispatch,
        patch.object(
            costs_api,
            "_anomaly_to_response_item",
            return_value=costs_api.CostAnomalyItem(
                day="2026-01-31",
                provider="aws",
                account_id="123456789012",
                account_name="prod",
                service="ec2",
                actual_cost_usd=100.0,
                expected_cost_usd=10.0,
                delta_cost_usd=90.0,
                percent_change=900.0,
                kind="spike",
                probable_cause="Burst workload",
                confidence=0.95,
                severity="high",
            ),
        ),
    ):
        response = await costs_api.get_cost_anomalies(
            target_date=date(2026, 1, 31),
            lookback_days=28,
            provider="aws",
            min_abs_usd=25.0,
            min_percent=30.0,
            min_severity="medium",
            alert=False,
            suppression_hours=24,
            user=user(),
            db=db,  # type: ignore[arg-type]
        )

    assert response.count == 1
    assert response.alerted_count == 0
    mock_dispatch.assert_not_awaited()
    service.detect.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_unit_economics_skips_alert_when_flag_disabled_with_anomaly() -> None:
    db = FakeDB()
    anomaly_metric = costs_api.UnitEconomicsMetric(
        metric_key="cost_per_request",
        label="Cost / Request",
        denominator=1000.0,
        total_cost=100.0,
        cost_per_unit=0.1,
        baseline_cost_per_unit=0.05,
        delta_percent=100.0,
        is_anomalous=True,
    )

    with (
        patch.object(
            costs_api,
            "_get_or_create_unit_settings",
            new=AsyncMock(
                return_value=standard_unit_settings(anomaly_threshold_percent=15.0)
            ),
        ),
        patch.object(
            costs_api,
            "_window_total_cost",
            new=AsyncMock(side_effect=[Decimal("100"), Decimal("90")]),
        ),
        patch.object(
            costs_api,
            "_build_unit_metrics",
            return_value=[anomaly_metric],
        ),
        patch.object(
            costs_api.NotificationDispatcher,
            "send_alert",
            new=AsyncMock(),
        ) as mock_alert,
    ):
        response = await costs_api.get_unit_economics(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider=None,
            request_volume=None,
            workload_volume=None,
            customer_volume=None,
            alert_on_anomaly=False,
            user=user(),
            db=db,  # type: ignore[arg-type]
        )

    assert response.anomaly_count == 1
    assert response.alert_dispatched is False
    mock_alert.assert_not_awaited()
