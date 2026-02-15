import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4
from datetime import date
from decimal import Decimal

from app.modules.reporting.domain.reconciliation import CostReconciliationService


@pytest.mark.asyncio
async def test_reconciliation_empty_results():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db.execute.return_value = mock_result

    service = CostReconciliationService(mock_db)
    tenant_id = uuid4()
    summary = await service.compare_explorer_vs_cur(
        tenant_id, date(2026, 1, 1), date(2026, 1, 2)
    )

    assert summary["tenant_id"] == str(tenant_id)
    assert summary["status"] == "no_comparable_data"
    assert summary["total_records"] == 0
    assert summary["total_cost"] == 0.0
    assert summary["discrepancies"] == []


@pytest.mark.asyncio
async def test_reconciliation_totals_with_none_values():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [
        MagicMock(service="EC2", total_cost=Decimal("10.50"), record_count=2),
        MagicMock(service="S3", total_cost=None, record_count=None),
    ]
    mock_db.execute.return_value = mock_result

    service = CostReconciliationService(mock_db)
    tenant_id = uuid4()
    summary = await service.compare_explorer_vs_cur(
        tenant_id, date(2026, 1, 1), date(2026, 1, 2)
    )

    assert summary["status"] == "no_comparable_data"
    assert summary["total_records"] == 2
    assert summary["total_cost"] == 10.5
