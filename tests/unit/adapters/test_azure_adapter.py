import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.shared.adapters.azure import AzureAdapter
from app.models.azure_connection import AzureConnection
from app.shared.core.exceptions import AdapterError


@pytest.fixture
def mock_azure_connection():
    return AzureConnection(
        azure_tenant_id="tenant-id",
        client_id="client-id",
        client_secret="client-secret",
        subscription_id="sub-id",
    )


@pytest.fixture
def azure_adapter(mock_azure_connection):
    return AzureAdapter(mock_azure_connection)


@pytest.mark.asyncio
async def test_azure_adapter_verify_connection_success(azure_adapter):
    mock_resource_client = (
        MagicMock()
    )  # Use MagicMock as list() is sync returning async iter

    # Mocking async for loop for Azure SDK
    class MockAsyncPager:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_resource_client.resource_groups.list.return_value = MockAsyncPager(
        [MagicMock()]
    )

    with patch.object(
        azure_adapter, "_get_resource_client", return_value=mock_resource_client
    ):
        result = await azure_adapter.verify_connection()
        assert result is True


@pytest.mark.asyncio
async def test_azure_adapter_verify_connection_failure(azure_adapter):
    with patch.object(
        azure_adapter, "_get_resource_client", side_effect=Exception("Azure Down")
    ):
        result = await azure_adapter.verify_connection()
        assert result is False


@pytest.mark.asyncio
async def test_azure_adapter_get_cost_and_usage_success(azure_adapter):
    mock_cost_client = AsyncMock()
    mock_response = MagicMock()
    # PreTaxCost (0), ServiceName (1), ResourceLocation (2), ChargeType (3), UsageDate (4)
    mock_response.rows = [[10.0, "Virtual Machines", "eastus", "Usage", "2026-01-01"]]
    mock_cost_client.query.usage.return_value = mock_response

    with patch.object(azure_adapter, "_get_cost_client", return_value=mock_cost_client):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        results = await azure_adapter.get_cost_and_usage(start, end)

        assert len(results) == 1
        assert results[0]["service"] == "Virtual Machines"
        assert results[0]["cost_usd"] == 10.0
        assert results[0]["region"] == "eastus"


@pytest.mark.asyncio
async def test_azure_adapter_get_cost_and_usage_failure(azure_adapter):
    mock_cost_client = AsyncMock()
    mock_cost_client.query.usage.side_effect = Exception("API Error")

    with patch.object(azure_adapter, "_get_cost_client", return_value=mock_cost_client):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with pytest.raises(AdapterError, match="Azure cost fetch failed"):
            await azure_adapter.get_cost_and_usage(start, end)


@pytest.mark.asyncio
async def test_azure_adapter_stream_cost_and_usage(azure_adapter):
    mock_records = [{"cost_usd": 5.0, "service": "S3"}]
    with patch.object(azure_adapter, "get_cost_and_usage", return_value=mock_records):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)

        results = []
        async for r in azure_adapter.stream_cost_and_usage(start, end):
            results.append(r)

        assert len(results) == 1
        assert results[0]["cost_usd"] == 5.0


@pytest.mark.asyncio
async def test_azure_adapter_discover_resources_success(azure_adapter):
    mock_resource_client = MagicMock()

    mock_res = MagicMock()
    mock_res.id = "id-1"
    mock_res.name = "res-1"
    mock_res.type = "Microsoft.Compute/virtualMachines"
    mock_res.location = "eastus"
    mock_res.tags = {"env": "prod"}

    # Mocking async for loop for Azure SDK
    class MockAsyncPager:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_resource_client.resources.list.return_value = MockAsyncPager([mock_res])

    with patch.object(
        azure_adapter, "_get_resource_client", return_value=mock_resource_client
    ):
        resources = await azure_adapter.discover_resources("virtualMachines", "eastus")
        assert len(resources) == 1
        assert resources[0]["name"] == "res-1"
        assert resources[0]["type"] == "Microsoft.Compute/virtualMachines"


@pytest.mark.asyncio
async def test_azure_adapter_discover_resources_error(azure_adapter):
    with patch.object(
        azure_adapter, "_get_resource_client", side_effect=Exception("Limit Exceeded")
    ):
        resources = await azure_adapter.discover_resources("compute")
        assert resources == []


def test_azure_adapter_parse_row_date_formats(azure_adapter):
    # Test different date formats Azure might return
    formats = ["20260101", "2026-01-01", "2026-01-01T00:00:00Z"]
    for fmt in formats:
        row = [10.0, "Svc", "Loc", "Type", fmt]
        parsed = azure_adapter._parse_row(row, "ActualCost")
        assert parsed["timestamp"].year == 2026
        assert parsed["timestamp"].month == 1
        assert parsed["timestamp"].day == 1
