import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from app.shared.adapters.azure import AzureAdapter
from app.models.azure_connection import AzureConnection
from app.shared.core.exceptions import AdapterError


@pytest.fixture
def mock_connection():
    conn = MagicMock(spec=AzureConnection)
    conn.tenant_id = "test-tenant-id"
    conn.azure_tenant_id = "az-tenant-id"
    conn.client_id = "client-id"
    conn.subscription_id = "sub-id"
    conn.client_secret = "secret"
    return conn


@pytest.fixture
def adapter(mock_connection):
    return AzureAdapter(mock_connection)


@pytest.mark.asyncio
async def test_azure_verify_connection_success(adapter):
    mock_rg_client = MagicMock()
    # Mock async iterator for resource_groups.list()
    mock_list = MagicMock()
    mock_list.__aiter__.return_value = [
        MagicMock()
    ].__iter__()  # Simplistic mock for async iter

    # Realistically, we need a better async iterator mock
    class AsyncIter:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_rg_client.resource_groups.list.return_value = AsyncIter([MagicMock()])

    with patch.object(
        AzureAdapter, "_get_resource_client", new_callable=AsyncMock
    ) as mock_get_client:
        mock_get_client.return_value = mock_rg_client
        result = await adapter.verify_connection()
        assert result is True


@pytest.mark.asyncio
async def test_azure_verify_connection_failure(adapter):
    with patch.object(
        AzureAdapter, "_get_resource_client", side_effect=Exception("Auth error")
    ):
        result = await adapter.verify_connection()
        assert result is False


@pytest.mark.asyncio
async def test_azure_get_cost_and_usage_success(adapter):
    mock_cost_client = MagicMock()
    mock_result = MagicMock()

    # Mock Azure QueryResult columns and rows
    mock_col_date = MagicMock()
    mock_col_date.name = "UsageDate"
    mock_col_cost = MagicMock()
    mock_col_cost.name = "PreTaxCost"
    mock_col_service = MagicMock()
    mock_col_service.name = "ServiceName"
    mock_col_currency = MagicMock()
    mock_col_currency.name = "Currency"

    mock_result.columns = [
        mock_col_cost,
        mock_col_service,
        mock_col_currency,
        mock_col_date,
    ]
    mock_result.rows = [
        [10.5, "Compute", "eastus", "Usage", "20240101"],
        [5.2, "Storage", "eastus", "Usage", "20240101"],
    ]

    mock_cost_client.query.usage = AsyncMock(return_value=mock_result)

    with patch.object(
        AzureAdapter, "_get_cost_client", new_callable=AsyncMock
    ) as mock_get_client:
        mock_get_client.return_value = mock_cost_client

        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 2)
        data = await adapter.get_cost_and_usage(start, end)

        assert len(data) == 2
        assert data[0]["cost_usd"] == 10.5
        assert data[0]["service"] == "Compute"
        assert isinstance(data[0]["timestamp"], datetime)
        assert data[0]["timestamp"].strftime("%Y-%m-%d") == "2024-01-01"


@pytest.mark.asyncio
async def test_azure_get_cost_and_usage_error(adapter):
    with patch.object(
        AzureAdapter, "_get_cost_client", side_effect=Exception("API Error")
    ):
        with pytest.raises(AdapterError):
            await adapter.get_cost_and_usage(datetime.now(), datetime.now())


@pytest.mark.asyncio
async def test_azure_discover_resources(adapter):
    mock_res_client = MagicMock()

    class AsyncIter:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    res1 = MagicMock()
    res1.id = "id1"
    res1.name = "vm1"
    res1.type = "Microsoft.Compute/virtualMachines"
    res1.location = "eastus"
    res1.tags = {}

    mock_res_client.resources.list.return_value = AsyncIter([res1])

    with patch.object(
        AzureAdapter, "_get_resource_client", new_callable=AsyncMock
    ) as mock_get_client:
        mock_get_client.return_value = mock_res_client
        resources = await adapter.discover_resources(resource_type="virtualMachines")

        assert len(resources) == 1
        assert resources[0]["name"] == "vm1"
        assert "virtualMachines" in resources[0]["type"]
