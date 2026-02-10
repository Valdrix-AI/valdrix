import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
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
