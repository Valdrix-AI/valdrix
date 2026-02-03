import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from app.shared.adapters.gcp import GCPAdapter
from app.shared.core.exceptions import AdapterError

@pytest.fixture
def mock_gcp_connection():
    return MagicMock(
        project_id="test-project",
        service_account_json='{"type": "service_account"}',
        billing_project_id="billing-project",
        billing_dataset="dataset",
        billing_table="table"
    )

@pytest.fixture
def gcp_adapter(mock_gcp_connection):
    return GCPAdapter(mock_gcp_connection)

@pytest.mark.asyncio
async def test_gcp_adapter_verify_connection_success(gcp_adapter):
    mock_client = MagicMock()
    # Mock some basic API call
    mock_client.list_datasets.return_value = []
    
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        result = await gcp_adapter.verify_connection()
        assert result is True

@pytest.mark.asyncio
async def test_gcp_adapter_verify_connection_failure(gcp_adapter):
    with patch("google.cloud.bigquery.Client", side_effect=Exception("Auth error")):
        result = await gcp_adapter.verify_connection()
        assert result is False

@pytest.mark.asyncio
async def test_gcp_adapter_get_cost_and_usage_success(gcp_adapter):
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    mock_row = MagicMock()
    mock_row.id = "id-1"
    mock_row.service = "Compute Engine"
    mock_row.cost_usd = 10.5
    mock_row.total_credits = 0.0
    mock_row.currency = "USD"
    mock_row.timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    
    mock_query_job.result.return_value = [mock_row]
    mock_client.query.return_value = mock_query_job
    
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        results = await gcp_adapter.get_cost_and_usage(start, end)
        
        assert len(results) == 1
        assert results[0]["service"] == "Compute Engine"
        assert results[0]["cost_usd"] == 10.5

@pytest.mark.asyncio
async def test_gcp_adapter_get_cost_and_usage_error(gcp_adapter):
    mock_client = MagicMock()
    mock_client.query.side_effect = Exception("BigQuery Error")
    
    with patch("google.cloud.bigquery.Client", return_value=mock_client):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with pytest.raises(AdapterError, match="GCP BigQuery cost fetch failed"):
            await gcp_adapter.get_cost_and_usage(start, end)

@pytest.mark.asyncio
async def test_gcp_adapter_discover_resources(gcp_adapter):
    mock_client = MagicMock()
    mock_instance = MagicMock()
    mock_instance.name = "vm-1"
    mock_instance.id = "123"
    mock_instance.status = "RUNNING"
    
    # Mocking pager
    mock_client.list_assets.return_value = [mock_instance]
    
    with patch("google.cloud.asset_v1.AssetServiceClient", return_value=mock_client):
        resources = await gcp_adapter.discover_resources("compute")
        assert len(resources) == 1
        assert resources[0]["name"] == "vm-1"
