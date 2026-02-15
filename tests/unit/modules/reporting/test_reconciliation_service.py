import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

from app.modules.reporting.domain.reconciliation import CostReconciliationService


@pytest.mark.asyncio
async def test_reconciliation_empty_results():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = []
    db.execute = AsyncMock(return_value=result)

    service = CostReconciliationService(db)
    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )

    assert summary["total_records"] == 0
    assert summary["total_cost"] == 0.0
    assert summary["discrepancies"] == []


@pytest.mark.asyncio
async def test_reconciliation_aggregates():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(record_count=2, total_cost=10.0, service="Compute"),
        SimpleNamespace(record_count=1, total_cost=5.5, service="Storage"),
    ]
    db.execute = AsyncMock(return_value=result)

    service = CostReconciliationService(db)
    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 28),
    )

    assert summary["total_records"] == 3
    assert summary["total_cost"] == 15.5


@pytest.mark.asyncio
async def test_reconciliation_handles_null_aggregates():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(record_count=None, total_cost=None, service="Compute"),
    ]
    db.execute = AsyncMock(return_value=result)

    service = CostReconciliationService(db)
    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2024, 3, 1),
        end_date=date(2024, 3, 31),
    )

    assert summary["total_records"] == 0
    assert summary["total_cost"] == 0.0


@pytest.mark.asyncio
async def test_reconciliation_detects_cross_source_discrepancy_and_alerts():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(
            service="Compute",
            source_adapter="cost_explorer",
            total_cost=105.0,
            record_count=10,
        ),
        SimpleNamespace(
            service="Compute",
            source_adapter="cur_parquet",
            total_cost=100.0,
            record_count=10,
        ),
        SimpleNamespace(
            service="Storage",
            source_adapter="cost_explorer",
            total_cost=50.0,
            record_count=3,
        ),
        SimpleNamespace(
            service="Storage",
            source_adapter="cur_parquet",
            total_cost=50.0,
            record_count=3,
        ),
    ]
    db.execute = AsyncMock(return_value=result)

    service = CostReconciliationService(db)
    with patch(
        "app.shared.core.notifications.NotificationDispatcher.send_alert",
        new=AsyncMock(),
    ) as mock_alert:
        summary = await service.compare_explorer_vs_cur(
            tenant_id=uuid4(),
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
            alert_threshold_pct=1.0,
        )

    assert summary["status"] == "warning"
    assert summary["discrepancy_percentage"] > 1.0
    assert summary["confidence"] > 0
    assert summary["alert_triggered"] is True
    assert len(summary["impacted_services"]) == 2
    assert len(summary["discrepancies"]) == 1
    mock_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconciliation_no_comparable_data_keeps_compatibility_totals():
    db = MagicMock()
    result = MagicMock()
    result.all.return_value = [
        SimpleNamespace(
            service="Compute", source_adapter="unknown", total_cost=20.0, record_count=2
        ),
    ]
    db.execute = AsyncMock(return_value=result)

    service = CostReconciliationService(db)
    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2024, 5, 1),
        end_date=date(2024, 5, 31),
    )

    assert summary["status"] == "no_comparable_data"
    assert summary["total_records"] == 2
    assert summary["total_cost"] == 20.0
    assert summary["discrepancies"] == []
