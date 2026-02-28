from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from app.shared.adapters.azure import AzureAdapter
from app.shared.core.credentials import AzureCredentials
from app.shared.core.exceptions import ConfigurationError


def _credentials(*, client_secret: str | None = "secret") -> AzureCredentials:
    return AzureCredentials(
        tenant_id="tenant-id",
        client_id="client-id",
        subscription_id="sub-id",
        client_secret=SecretStr(client_secret) if client_secret is not None else None,
    )


def _async_pager(items: list[object]):
    class _Pager:
        def __init__(self, values: list[object]) -> None:
            self._values = list(values)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._values:
                raise StopAsyncIteration
            return self._values.pop(0)

    return _Pager(items)


@pytest.mark.asyncio
async def test_get_credentials_requires_client_secret() -> None:
    adapter = AzureAdapter(_credentials(client_secret=None))

    with pytest.raises(ConfigurationError, match="client_secret is required"):
        await adapter._get_credentials()


@pytest.mark.asyncio
async def test_get_credentials_and_clients_are_cached() -> None:
    adapter = AzureAdapter(_credentials())

    fake_credential = object()
    fake_cost_client = object()
    fake_resource_client = object()
    fake_compute_client = object()

    with (
        patch(
            "app.shared.adapters.azure.ClientSecretCredential",
            return_value=fake_credential,
        ) as credential_cls,
        patch(
            "app.shared.adapters.azure.CostManagementClient",
            return_value=fake_cost_client,
        ) as cost_cls,
        patch(
            "app.shared.adapters.azure.ResourceManagementClient",
            return_value=fake_resource_client,
        ) as resource_cls,
        patch(
            "app.shared.adapters.azure.ComputeManagementClient",
            return_value=fake_compute_client,
        ) as compute_cls,
    ):
        assert await adapter._get_credentials() is fake_credential
        assert await adapter._get_credentials() is fake_credential

        assert await adapter._get_cost_client() is fake_cost_client
        assert await adapter._get_cost_client() is fake_cost_client

        assert await adapter._get_resource_client() is fake_resource_client
        assert await adapter._get_resource_client() is fake_resource_client

        assert await adapter._get_compute_client() is fake_compute_client
        assert await adapter._get_compute_client() is fake_compute_client

    credential_cls.assert_called_once()
    cost_cls.assert_called_once()
    resource_cls.assert_called_once()
    compute_cls.assert_called_once()


def test_parse_row_iso_fallback_handles_naive_and_offset_datetimes() -> None:
    adapter = AzureAdapter(_credentials())

    naive_row = [1.0, "Compute", "eastus", "Usage", "2026-01-10T00:00:00"]
    offset_row = [2.0, "Storage", "westus", "Usage", "2026-01-10T03:30:00+03:30"]

    naive = adapter._parse_row(naive_row, "ActualCost")
    offset = adapter._parse_row(offset_row, "ActualCost")

    assert naive["timestamp"].tzinfo is not None
    assert naive["timestamp"].utcoffset().total_seconds() == 0
    assert offset["timestamp"].tzinfo is not None
    assert offset["timestamp"].utcoffset().total_seconds() == 0


@pytest.mark.asyncio
async def test_get_daily_costs_skips_non_positive_and_disables_service_grouping() -> None:
    adapter = AzureAdapter(_credentials())
    rows = [
        {
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "service": "Compute",
            "region": "eastus",
            "cost_usd": 0,
            "currency": "USD",
            "amount_raw": 0,
            "usage_type": "Usage",
        },
        {
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "service": "Compute",
            "region": "eastus",
            "cost_usd": 12.5,
            "currency": "USD",
            "amount_raw": 12.5,
            "usage_type": "Usage",
            "tags": {"env": "prod"},
        },
    ]

    with patch.object(adapter, "get_cost_and_usage", AsyncMock(return_value=rows)):
        summary = await adapter.get_daily_costs(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            group_by_service=False,
        )

    assert str(summary.total_cost) == "12.5"
    assert len(summary.records) == 1
    assert summary.by_service == {}


@pytest.mark.asyncio
async def test_get_amortized_costs_delegates_with_cost_type() -> None:
    adapter = AzureAdapter(_credentials())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with patch.object(
        adapter, "get_cost_and_usage", AsyncMock(return_value=[{"cost_usd": 1}])
    ) as mock_fetch:
        result = await adapter.get_amortized_costs(start, end, granularity="MONTHLY")

    assert result == [{"cost_usd": 1}]
    mock_fetch.assert_awaited_once_with(
        start, end, "MONTHLY", cost_type="AmortizedCost"
    )


@pytest.mark.asyncio
async def test_discover_resources_filters_non_compute_type_and_region() -> None:
    adapter = AzureAdapter(_credentials())
    mock_client = MagicMock()

    wrong_type = SimpleNamespace(
        id="1",
        name="storage-1",
        type="Microsoft.Storage/storageAccounts",
        location="eastus",
        tags=None,
    )
    wrong_region = SimpleNamespace(
        id="2",
        name="vm-west",
        type="Microsoft.Compute/virtualMachines",
        location="westus",
        tags={},
    )
    match = SimpleNamespace(
        id="3",
        name="vm-east",
        type="Microsoft.Compute/virtualMachines",
        location="eastus",
        tags={"env": "prod"},
    )
    mock_client.resources.list.return_value = _async_pager([wrong_type, wrong_region, match])

    with patch.object(adapter, "_get_resource_client", AsyncMock(return_value=mock_client)):
        results = await adapter.discover_resources("virtualMachines", region="eastus")

    assert [r["name"] for r in results] == ["vm-east"]


@pytest.mark.asyncio
async def test_get_resource_usage_projects_and_filters_rows() -> None:
    adapter = AzureAdapter(_credentials())
    rows = [
        {
            "timestamp": datetime(2026, 1, 15, tzinfo=timezone.utc),
            "service": "Compute",
            "resource_id": "vm-1",
            "usage_type": "vm_hours",
            "usage_amount": 24,
            "usage_unit": "hour",
            "cost_usd": 12.5,
            "currency": "USD",
            "amount_raw": 12.5,
            "region": "eastus",
            "source_adapter": "explorer_api",
        },
        {
            "timestamp": datetime(2026, 1, 15, tzinfo=timezone.utc),
            "service": "Storage",
            "resource_id": "disk-1",
            "cost_usd": 3.0,
            "currency": "USD",
        },
    ]
    with patch.object(
        adapter, "get_cost_and_usage", AsyncMock(return_value=rows)
    ) as mock_fetch:
        usage_rows = await adapter.get_resource_usage("compute", "vm-1")

    assert len(usage_rows) == 1
    assert usage_rows[0]["provider"] == "azure"
    assert usage_rows[0]["service"] == "Compute"
    assert usage_rows[0]["resource_id"] == "vm-1"
    assert usage_rows[0]["usage_unit"] == "hour"
    assert usage_rows[0]["source_adapter"] == "explorer_api"
    assert mock_fetch.await_count == 1
    assert mock_fetch.await_args.kwargs["granularity"] == "DAILY"


@pytest.mark.asyncio
async def test_get_resource_usage_failure_returns_empty_and_sets_error() -> None:
    adapter = AzureAdapter(_credentials())
    with patch.object(
        adapter,
        "get_cost_and_usage",
        AsyncMock(side_effect=RuntimeError("azure usage failure")),
    ):
        assert await adapter.get_resource_usage("compute", "vm-1") == []

    assert adapter.last_error is not None
    assert "Azure resource usage lookup failed" in adapter.last_error
