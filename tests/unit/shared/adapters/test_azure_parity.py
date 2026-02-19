import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace

from app.shared.adapters.azure import AzureAdapter
from app.models.azure_connection import AzureConnection
from app.schemas.costs import CloudUsageSummary


def _connection():
    return AzureConnection(
        tenant_id=uuid4(),
        name="Test",
        azure_tenant_id="tenant",
        client_id="client",
        subscription_id="sub",
        client_secret="secret",
    )


@pytest.mark.asyncio
async def test_get_daily_costs_success():
    adapter = AzureAdapter(_connection())
    # PreTaxCost (0), ServiceName (1), ResourceLocation (2), ChargeType (3), UsageDate (4)
    row = [2.5, "Compute", "eastus", "Usage", "20240101"]
    mock_client = MagicMock()
    mock_client.query.usage = AsyncMock(return_value=SimpleNamespace(rows=[row]))

    with patch.object(adapter, "_get_cost_client", AsyncMock(return_value=mock_client)):
        summary = await adapter.get_daily_costs(
            date(2024, 1, 1),
            date(2024, 1, 2),
        )

    assert isinstance(summary, CloudUsageSummary)
    assert summary.total_cost == Decimal("2.5")
    assert len(summary.records) == 1
    assert summary.records[0].service == "Compute"
    assert summary.records[0].amount == Decimal("2.5")
    assert summary.provider == "azure"

@pytest.mark.asyncio
async def test_get_daily_costs_empty():
    adapter = AzureAdapter(_connection())
    mock_client = MagicMock()
    mock_client.query.usage = AsyncMock(return_value=SimpleNamespace(rows=[]))

    with patch.object(adapter, "_get_cost_client", AsyncMock(return_value=mock_client)):
        summary = await adapter.get_daily_costs(
            date(2024, 1, 1),
            date(2024, 1, 2),
        )

    assert summary.total_cost == Decimal("0")
    assert len(summary.records) == 0
