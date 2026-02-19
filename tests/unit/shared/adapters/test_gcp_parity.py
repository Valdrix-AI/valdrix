import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.shared.adapters.gcp import GCPAdapter
from app.models.gcp_connection import GCPConnection
from app.schemas.costs import CloudUsageSummary


def _connection():
    return GCPConnection(
        tenant_id=uuid4(),
        name="Test",
        project_id="test-project",
        billing_dataset="billing_ds",
        billing_table="billing_tbl",
    )


@pytest.mark.asyncio
async def test_get_daily_costs_success():
    adapter = GCPAdapter(_connection())
    
    mock_row = MagicMock()
    mock_row.service = "Compute Engine"
    mock_row.cost_usd = 10.5
    mock_row.total_credits = -2.0
    mock_row.currency = "USD"
    mock_row.timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)

    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = [mock_row]

    with patch.object(adapter, "_get_bq_client", return_value=mock_bq):
        summary = await adapter.get_daily_costs(
            date(2024, 1, 1),
            date(2024, 1, 1),
        )

    assert isinstance(summary, CloudUsageSummary)
    assert summary.total_cost == Decimal("10.5")
    assert len(summary.records) == 1
    assert summary.records[0].service == "Compute Engine"
    assert summary.records[0].amount == Decimal("10.5")
    assert summary.provider == "gcp"

@pytest.mark.asyncio
async def test_get_daily_costs_empty():
    adapter = GCPAdapter(_connection())
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = []

    with patch.object(adapter, "_get_bq_client", return_value=mock_bq):
        summary = await adapter.get_daily_costs(
            date(2024, 1, 1),
            date(2024, 1, 1),
        )

    assert summary.total_cost == Decimal("0")
    assert len(summary.records) == 0
