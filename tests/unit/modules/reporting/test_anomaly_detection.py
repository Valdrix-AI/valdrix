from unittest.mock import AsyncMock, patch

import pytest
from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.modules.reporting.domain.anomaly_detection import (
    DailyServiceCostRow,
    CostAnomaly,
    detect_daily_cost_anomalies,
    dispatch_cost_anomaly_alerts,
    severity_gte,
)


def _row(day: date, cost: str, *, service: str = "AmazonEC2") -> DailyServiceCostRow:
    return DailyServiceCostRow(
        day=day,
        provider="aws",
        account_id=uuid4(),
        account_name="Prod AWS",
        service=service,
        cost_usd=Decimal(cost),
    )


def test_detect_new_spend_anomaly() -> None:
    account_id = uuid4()
    rows: list[DailyServiceCostRow] = []
    for d in range(1, 29):
        rows.append(
            DailyServiceCostRow(
                day=date(2026, 1, d),
                provider="aws",
                account_id=account_id,
                account_name="Prod AWS",
                service="AmazonEKS",
                cost_usd=Decimal("0"),
            )
        )
    rows.append(
        DailyServiceCostRow(
            day=date(2026, 1, 29),
            provider="aws",
            account_id=account_id,
            account_name="Prod AWS",
            service="AmazonEKS",
            cost_usd=Decimal("220.00"),
        )
    )

    anomalies = detect_daily_cost_anomalies(
        rows,
        target_date=date(2026, 1, 29),
        lookback_days=28,
        min_abs_usd=Decimal("25"),
        min_percent=30.0,
    )

    assert len(anomalies) == 1
    assert anomalies[0].kind == "new_spend"
    assert anomalies[0].probable_cause == "new_service_spend"
    assert anomalies[0].severity in {"medium", "high", "critical"}


def test_detect_spike_with_weekday_baseline() -> None:
    account_id = uuid4()
    rows: list[DailyServiceCostRow] = []
    # Stable baseline around 100/day
    for d in range(1, 29):
        rows.append(
            DailyServiceCostRow(
                day=date(2026, 1, d),
                provider="aws",
                account_id=account_id,
                account_name="Prod AWS",
                service="AmazonEC2",
                cost_usd=Decimal("100.00"),
            )
        )
    # Target spike
    rows.append(
        DailyServiceCostRow(
            day=date(2026, 1, 29),
            provider="aws",
            account_id=account_id,
            account_name="Prod AWS",
            service="AmazonEC2",
            cost_usd=Decimal("350.00"),
        )
    )

    anomalies = detect_daily_cost_anomalies(
        rows,
        target_date=date(2026, 1, 29),
        lookback_days=28,
        min_abs_usd=Decimal("25"),
        min_percent=30.0,
    )

    assert len(anomalies) == 1
    item = anomalies[0]
    assert item.kind == "spike"
    assert item.percent_change is not None
    assert item.percent_change >= 200.0
    assert item.confidence > 0.0
    assert severity_gte(item.severity, "medium")


def test_sparse_drop_not_flagged() -> None:
    account_id = uuid4()
    rows: list[DailyServiceCostRow] = []
    # Only two active baseline days (too sparse for drop).
    rows.extend(
        [
            DailyServiceCostRow(
                day=date(2026, 1, 5),
                provider="aws",
                account_id=account_id,
                account_name="Prod AWS",
                service="AWSLambda",
                cost_usd=Decimal("100.00"),
            ),
            DailyServiceCostRow(
                day=date(2026, 1, 12),
                provider="aws",
                account_id=account_id,
                account_name="Prod AWS",
                service="AWSLambda",
                cost_usd=Decimal("100.00"),
            ),
            DailyServiceCostRow(
                day=date(2026, 1, 29),
                provider="aws",
                account_id=account_id,
                account_name="Prod AWS",
                service="AWSLambda",
                cost_usd=Decimal("0.00"),
            ),
        ]
    )

    anomalies = detect_daily_cost_anomalies(
        rows,
        target_date=date(2026, 1, 29),
        lookback_days=28,
        min_abs_usd=Decimal("25"),
        min_percent=30.0,
    )

    assert anomalies == []


@pytest.mark.asyncio
async def test_dispatch_cost_anomaly_alerts_suppresses_by_fingerprint() -> None:
    tenant_id = uuid4()
    anomaly = CostAnomaly(
        day=date(2026, 1, 29),
        provider="aws",
        account_id=uuid4(),
        account_name="Prod AWS",
        service="AmazonEC2",
        actual_cost_usd=Decimal("350.00"),
        expected_cost_usd=Decimal("100.00"),
        delta_cost_usd=Decimal("250.00"),
        percent_change=250.0,
        kind="spike",
        probable_cause="spend_spike",
        confidence=0.9,
        severity="high",
    )

    with patch(
        "app.modules.reporting.domain.anomaly_detection.CacheService"
    ) as cache_cls:
        cache = cache_cls.return_value
        cache.get = AsyncMock(side_effect=[None, {"ts": "seen"}])
        cache.set = AsyncMock(return_value=True)

        with patch(
            "app.modules.reporting.domain.anomaly_detection.NotificationDispatcher.send_alert",
            new_callable=AsyncMock,
        ) as send_alert:
            first = await dispatch_cost_anomaly_alerts(
                tenant_id=tenant_id,
                anomalies=[anomaly],
                suppression_hours=24,
                db=None,
            )
            second = await dispatch_cost_anomaly_alerts(
                tenant_id=tenant_id,
                anomalies=[anomaly],
                suppression_hours=24,
                db=None,
            )

            assert first == 1
            assert second == 0
            assert send_alert.call_count == 1


@pytest.mark.asyncio
async def test_dispatch_cost_anomaly_alerts_creates_jira_issue_for_high_severity_when_enabled() -> (
    None
):
    from app.shared.core.pricing import PricingTier

    tenant_id = uuid4()
    anomaly = CostAnomaly(
        day=date(2026, 1, 29),
        provider="aws",
        account_id=uuid4(),
        account_name="Prod AWS",
        service="AmazonEC2",
        actual_cost_usd=Decimal("350.00"),
        expected_cost_usd=Decimal("100.00"),
        delta_cost_usd=Decimal("250.00"),
        percent_change=250.0,
        kind="spike",
        probable_cause="spend_spike",
        confidence=0.9,
        severity="high",
    )

    fake_db = AsyncMock()
    fake_jira = AsyncMock()

    with patch(
        "app.shared.core.pricing.get_tenant_tier",
        new=AsyncMock(return_value=PricingTier.PRO),
    ):
        with patch("app.shared.core.pricing.is_feature_enabled", return_value=True):
            with patch(
                "app.modules.notifications.domain.get_tenant_jira_service",
                new=AsyncMock(return_value=fake_jira),
            ):
                with patch(
                    "app.modules.reporting.domain.anomaly_detection.CacheService"
                ) as cache_cls:
                    cache = cache_cls.return_value
                    cache.get = AsyncMock(return_value=None)
                    cache.set = AsyncMock(return_value=True)

                    with patch(
                        "app.modules.reporting.domain.anomaly_detection.NotificationDispatcher.send_alert",
                        new_callable=AsyncMock,
                    ):
                        with patch(
                            "app.modules.reporting.domain.anomaly_detection.NotificationDispatcher._dispatch_workflow_event",
                            new_callable=AsyncMock,
                        ):
                            alerted = await dispatch_cost_anomaly_alerts(
                                tenant_id=tenant_id,
                                anomalies=[anomaly],
                                suppression_hours=24,
                                db=fake_db,
                            )

    assert alerted == 1
    assert fake_jira.create_cost_anomaly_issue.call_count == 1
