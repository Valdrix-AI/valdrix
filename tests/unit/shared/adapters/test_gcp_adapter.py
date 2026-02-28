import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from app.shared.adapters.gcp import GCPAdapter, validate_project_id
from app.models.gcp_connection import GCPConnection
from app.shared.core.exceptions import AdapterError, ConfigurationError


def _connection(**kwargs):
    data = {
        "tenant_id": uuid4(),
        "name": "Test",
        "project_id": "proj-12345",
        "service_account_json": None,
        "billing_project_id": None,
        "billing_dataset": None,
        "billing_table": None,
    }
    data.update(kwargs)
    return GCPConnection(**data)


def test_validate_project_id():
    assert validate_project_id("proj-12345") is True
    assert validate_project_id("BAD_PROJECT") is False


def test_invalid_project_id_raises():
    conn = _connection(project_id="BAD_PROJECT")
    with pytest.raises(ConfigurationError):
        GCPAdapter(conn)


def test_credentials_invalid_json_returns_none():
    conn = _connection(service_account_json="{bad-json}")
    with patch(
        "app.shared.adapters.gcp.service_account.Credentials.from_service_account_info",
        side_effect=ValueError("bad"),
    ):
        adapter = GCPAdapter(conn)
    assert adapter._credentials is None


@pytest.mark.asyncio
async def test_verify_connection_success():
    adapter = GCPAdapter(_connection())
    adapter.last_error = "stale"
    client = MagicMock()
    client.list_datasets.return_value = []
    with patch.object(adapter, "_get_bq_client", return_value=client):
        assert await adapter.verify_connection() is True
    assert adapter.last_error is None


@pytest.mark.asyncio
async def test_verify_connection_failure():
    adapter = GCPAdapter(_connection())
    client = MagicMock()
    client.list_datasets.side_effect = RuntimeError("boom")
    with patch.object(adapter, "_get_bq_client", return_value=client):
        assert await adapter.verify_connection() is False
    assert adapter.last_error is not None
    assert "GCP credential verification failed" in adapter.last_error


@pytest.mark.asyncio
async def test_get_cost_and_usage_missing_export_returns_empty():
    adapter = GCPAdapter(_connection())
    with patch.object(adapter, "_get_bq_client") as mock_client:
        results = await adapter.get_cost_and_usage(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )
        assert results == []
        mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_get_cost_and_usage_invalid_table_path():
    adapter = GCPAdapter(
        _connection(
            billing_project_id="proj-12345",
            billing_dataset="bad-dataset!",
            billing_table="table",
        )
    )
    with patch.object(adapter, "_get_bq_client", return_value=MagicMock()):
        with pytest.raises(ConfigurationError):
            await adapter.get_cost_and_usage(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )


@pytest.mark.asyncio
async def test_get_cost_and_usage_query_error():
    adapter = GCPAdapter(
        _connection(
            billing_project_id="proj-12345",
            billing_dataset="dataset",
            billing_table="table",
        )
    )
    client = MagicMock()
    client.query.side_effect = RuntimeError("query failed")
    with patch.object(adapter, "_get_bq_client", return_value=client):
        with pytest.raises(AdapterError):
            await adapter.get_cost_and_usage(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )


@pytest.mark.asyncio
async def test_discover_resources_success():
    adapter = GCPAdapter(_connection())
    asset_client = MagicMock()
    asset = SimpleNamespace(
        name="projects/proj-12345/assets/1",
        asset_type="compute.googleapis.com/Instance",
        resource=SimpleNamespace(data={"foo": "bar"}),
    )
    asset_client.list_assets.return_value = [asset]
    with patch.object(adapter, "_get_asset_client", return_value=asset_client):
        results = await adapter.discover_resources(resource_type="compute")
    assert len(results) == 1
    assert results[0]["provider"] == "gcp"


@pytest.mark.asyncio
async def test_discover_resources_failure_returns_empty():
    adapter = GCPAdapter(_connection())
    asset_client = MagicMock()
    asset_client.list_assets.side_effect = RuntimeError("boom")
    with patch.object(adapter, "_get_asset_client", return_value=asset_client):
        results = await adapter.discover_resources(resource_type="compute")
    assert results == []


@pytest.mark.asyncio
async def test_get_resource_usage_projects_and_filters_rows():
    adapter = GCPAdapter(_connection())
    rows = [
        {
            "timestamp": datetime(2026, 1, 10, tzinfo=timezone.utc),
            "service": "Compute Engine",
            "resource_id": "projects/p1/zones/us-central1-a/instances/vm-1",
            "usage_type": "instance_hour",
            "usage_amount": "12",
            "cost_usd": 6.5,
            "currency": "USD",
            "region": "us-central1",
            "source_adapter": "cur_billing_export",
        },
        {
            "timestamp": datetime(2026, 1, 10, tzinfo=timezone.utc),
            "service": "Cloud Storage",
            "resource_id": "projects/_/buckets/b-1",
            "cost_usd": 1.2,
            "currency": "USD",
        },
    ]

    with patch.object(
        adapter, "get_cost_and_usage", AsyncMock(return_value=rows)
    ) as mock_fetch:
        usage_rows = await adapter.get_resource_usage(
            "compute", "projects/p1/zones/us-central1-a/instances/vm-1"
        )

    assert len(usage_rows) == 1
    assert usage_rows[0]["provider"] == "gcp"
    assert usage_rows[0]["service"] == "Compute Engine"
    assert usage_rows[0]["resource_id"].endswith("vm-1")
    # usage_amount is present; unit defaults to "unit" when not provided.
    assert usage_rows[0]["usage_unit"] == "unit"
    assert mock_fetch.await_count == 1
    assert mock_fetch.await_args.kwargs["granularity"] == "DAILY"


@pytest.mark.asyncio
async def test_get_resource_usage_failure_returns_empty_and_sets_error():
    adapter = GCPAdapter(_connection())
    with patch.object(
        adapter,
        "get_cost_and_usage",
        AsyncMock(side_effect=RuntimeError("gcp usage failure")),
    ):
        assert await adapter.get_resource_usage("compute") == []

    assert adapter.last_error is not None
    assert "GCP resource usage lookup failed" in adapter.last_error
