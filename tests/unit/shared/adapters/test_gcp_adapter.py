import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4
from types import SimpleNamespace

from app.shared.adapters.gcp import GCPAdapter, validate_project_id
from app.models.gcp_connection import GCPConnection
from app.shared.core.exceptions import AdapterError


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
    with pytest.raises(ValueError):
        GCPAdapter(conn)


def test_credentials_invalid_json_returns_none():
    conn = _connection(service_account_json="{bad-json}")
    with patch("app.shared.adapters.gcp.service_account.Credentials.from_service_account_info", side_effect=ValueError("bad")):
        adapter = GCPAdapter(conn)
    assert adapter._credentials is None


@pytest.mark.asyncio
async def test_verify_connection_success():
    adapter = GCPAdapter(_connection())
    client = MagicMock()
    client.list_datasets.return_value = []
    with patch.object(adapter, "_get_bq_client", return_value=client):
        assert await adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_verify_connection_failure():
    adapter = GCPAdapter(_connection())
    client = MagicMock()
    client.list_datasets.side_effect = RuntimeError("boom")
    with patch.object(adapter, "_get_bq_client", return_value=client):
        assert await adapter.verify_connection() is False


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
    adapter = GCPAdapter(_connection(
        billing_project_id="proj-12345",
        billing_dataset="bad-dataset!",
        billing_table="table",
    ))
    with patch.object(adapter, "_get_bq_client", return_value=MagicMock()):
        with pytest.raises(ValueError):
            await adapter.get_cost_and_usage(
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            )


@pytest.mark.asyncio
async def test_get_cost_and_usage_query_error():
    adapter = GCPAdapter(_connection(
        billing_project_id="proj-12345",
        billing_dataset="dataset",
        billing_table="table",
    ))
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
        resource=SimpleNamespace(data={"foo": "bar"})
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
