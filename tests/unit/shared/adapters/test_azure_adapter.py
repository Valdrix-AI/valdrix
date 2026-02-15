import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from app.shared.adapters.azure import AzureAdapter
from app.models.azure_connection import AzureConnection
from app.shared.core.exceptions import AdapterError


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
async def test_verify_connection_success():
    adapter = AzureAdapter(_connection())
    mock_client = MagicMock()

    async def list_groups():
        if False:
            yield None
        return

    mock_client.resource_groups.list = list_groups

    with patch.object(
        adapter, "_get_resource_client", AsyncMock(return_value=mock_client)
    ):
        assert await adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_verify_connection_failure():
    adapter = AzureAdapter(_connection())
    with patch.object(
        adapter, "_get_resource_client", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await adapter.verify_connection() is False


def test_parse_row_invalid_date_falls_back():
    adapter = AzureAdapter(_connection())
    row = [1.0, "Compute", "eastus", "Usage", "bad-date"]

    with patch("dateutil.parser.parse", side_effect=ValueError("bad-date")):
        result = adapter._parse_row(row, "ActualCost")

    assert result["timestamp"].tzinfo is not None
    assert result["cost_usd"] == 1.0


@pytest.mark.asyncio
async def test_get_cost_and_usage_success():
    adapter = AzureAdapter(_connection())
    row = [2.5, "Compute", "eastus", "Usage", "20240101"]
    mock_client = MagicMock()
    mock_client.query.usage = AsyncMock(return_value=SimpleNamespace(rows=[row]))

    with patch.object(adapter, "_get_cost_client", AsyncMock(return_value=mock_client)):
        results = await adapter.get_cost_and_usage(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )

    assert len(results) == 1
    assert results[0]["service"] == "Compute"


@pytest.mark.asyncio
async def test_get_cost_and_usage_error_raises_adapter_error():
    adapter = AzureAdapter(_connection())
    mock_client = MagicMock()
    mock_client.query.usage = AsyncMock(side_effect=RuntimeError("query failed"))

    with patch.object(adapter, "_get_cost_client", AsyncMock(return_value=mock_client)):
        with pytest.raises(AdapterError):
            await adapter.get_cost_and_usage(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )


@pytest.mark.asyncio
async def test_discover_resources_filters_by_type_and_region():
    adapter = AzureAdapter(_connection())
    mock_client = MagicMock()

    res1 = SimpleNamespace(
        id="1",
        name="vm-1",
        type="Microsoft.Compute/virtualMachines",
        location="eastus",
        tags={"env": "prod"},
    )
    res2 = SimpleNamespace(
        id="2",
        name="storage-1",
        type="Microsoft.Storage/storageAccounts",
        location="westus",
        tags=None,
    )

    async def list_resources():
        yield res1
        yield res2

    mock_client.resources.list = list_resources

    with patch.object(
        adapter, "_get_resource_client", AsyncMock(return_value=mock_client)
    ):
        results = await adapter.discover_resources(
            resource_type="compute", region="eastus"
        )

    assert len(results) == 1
    assert results[0]["name"] == "vm-1"


@pytest.mark.asyncio
async def test_discover_resources_exception_returns_empty():
    adapter = AzureAdapter(_connection())
    with patch.object(
        adapter, "_get_resource_client", AsyncMock(side_effect=RuntimeError("boom"))
    ):
        results = await adapter.discover_resources(resource_type="compute")
    assert results == []
