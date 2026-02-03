import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from decimal import Decimal
from botocore.exceptions import ClientError
from app.shared.adapters.aws import AWSAdapter
from app.shared.core.exceptions import AdapterError
from app.models.aws_connection import AWSConnection

@pytest.fixture
def aws_adapter():
    mock_connection = AsyncMock(spec=AWSConnection)
    mock_connection.tenant_id = "test-tenant"
    mock_connection.aws_account_id = "123456789012"
    mock_connection.role_arn = "arn:aws:iam::123456789012:role/test"
    mock_connection.external_id = "test-external-id"
    mock_connection.region = "us-east-1"
    return AWSAdapter(connection=mock_connection)

@pytest.mark.asyncio
async def test_aws_adapter_verify_connection(aws_adapter):
    assert await aws_adapter.verify_connection() is True

@pytest.mark.asyncio
async def test_aws_adapter_get_cost_and_usage_success(aws_adapter):
    mock_results = [{"TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"}, "Total": {"UnblendedCost": {"Amount": "10.0", "Unit": "USD"}}}]
    
    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.return_value = {"ResultsByTime": mock_results}
    
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    
    with patch.object(aws_adapter.session, "client", return_value=mock_cm):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        results = await aws_adapter.get_cost_and_usage(start, end)
        
        assert len(results) == 1
        assert results[0] == mock_results[0]
        mock_client.get_cost_and_usage.assert_called_once()

@pytest.mark.asyncio
async def test_aws_adapter_get_cost_and_usage_client_error(aws_adapter):
    error_response = {"Error": {"Code": "AccessDeniedException", "Message": "No access"}}
    client_error = ClientError(error_response, "GetCostAndUsage")
    
    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.side_effect = client_error
    
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    
    with patch.object(aws_adapter.session, "client", return_value=mock_cm):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        with pytest.raises(AdapterError) as excinfo:
            await aws_adapter.get_cost_and_usage(start, end)
        
        assert "AWS Cost Explorer fetch failed" in str(excinfo.value)
        assert excinfo.value.code == "AccessDeniedException"

@pytest.mark.asyncio
async def test_aws_adapter_stream_cost_and_usage(aws_adapter):
    mock_results = [{
        "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
        "Total": {"UnblendedCost": {"Amount": "15.5", "Unit": "USD"}}
    }]
    
    with patch.object(aws_adapter, "get_daily_costs", return_value=mock_results):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 1, 2, tzinfo=timezone.utc)
        
        stream_results = []
        async for item in aws_adapter.stream_cost_and_usage(start, end):
            stream_results.append(item)
            
        assert len(stream_results) == 1
        assert stream_results[0]["cost_usd"] == Decimal("15.5")
        assert stream_results[0]["service"] == "Total"
        assert stream_results[0]["timestamp"] == datetime(2026, 1, 1, tzinfo=timezone.utc)

@pytest.mark.asyncio
async def test_aws_adapter_discover_resources(aws_adapter):
    # Coverage for empty list return
    resources = await aws_adapter.discover_resources("ec2")
    assert resources == []

@pytest.mark.asyncio
async def test_aws_adapter_get_resource_usage(aws_adapter):
    # Coverage for empty list return
    usage = await aws_adapter.get_resource_usage("ec2", "i-123")
    assert usage == []
