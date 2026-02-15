import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from datetime import datetime, timezone
from decimal import Decimal
from botocore.exceptions import ClientError
from app.shared.adapters.aws import AWSAdapter
from app.shared.core.exceptions import AdapterError
from app.models.aws_connection import AWSConnection


@pytest.fixture
def mock_session():
    # Patch aioboto3 Session at the module level
    with patch(
        "app.shared.adapters.aws_multitenant.aioboto3.Session"
    ) as mock_session_cls:
        session_instance = MagicMock()
        mock_session_cls.return_value = session_instance
        yield session_instance


@pytest.fixture
def aws_adapter(mock_session):
    mock_connection = AsyncMock(spec=AWSConnection)
    mock_connection.tenant_id = "test-tenant"
    mock_connection.aws_account_id = "123456789012"
    mock_connection.role_arn = "arn:aws:iam::123456789012:role/test"
    mock_connection.external_id = "test-external-id"
    mock_connection.region = "us-east-1"

    # Patch get_credentials at the class level so instances use the mock
    with patch(
        "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter.get_credentials",
        new_callable=AsyncMock,
    ) as mock_get_creds:
        mock_get_creds.return_value = {
            "AccessKeyId": "AK",
            "SecretAccessKey": "SK",
            "SessionToken": "ST",
            "Expiration": datetime.now(timezone.utc),
        }
        adapter = AWSAdapter(connection=mock_connection)
        adapter.session = mock_session
        yield adapter


@pytest.mark.asyncio
async def test_aws_adapter_verify_connection(aws_adapter):
    # verification passes if get_credentials finishes without error
    assert await aws_adapter.verify_connection() is True

    mock_results_with_groups = [
        {
            "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
            "Groups": [
                {
                    "Keys": ["Total"],
                    "Metrics": {"AmortizedCost": {"Amount": "10.0", "Unit": "USD"}},
                }
            ],
        }
    ]

    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.return_value = {
        "ResultsByTime": mock_results_with_groups
    }

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            pass

    aws_adapter.session.client.return_value = AsyncContextManagerMock()

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    results = await aws_adapter.get_cost_and_usage(start, end)

    assert len(results) == 1
    assert results[0]["cost_usd"] == Decimal("10.0")


@pytest.mark.asyncio
async def test_aws_adapter_get_cost_and_usage_client_error(aws_adapter):
    error_response = {
        "Error": {"Code": "AccessDeniedException", "Message": "No access"}
    }
    client_error = ClientError(error_response, "GetCostAndUsage")

    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.side_effect = client_error

    # Native async context manager support
    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            pass

    aws_adapter.session.client.return_value = AsyncContextManagerMock()

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    with pytest.raises(AdapterError) as excinfo:
        await aws_adapter.get_cost_and_usage(start, end)

    assert "Permission denied" in str(excinfo.value)

    assert excinfo.value.code == "AccessDeniedException"


@pytest.mark.asyncio
async def test_aws_adapter_stream_cost_and_usage(aws_adapter):
    stream_results = []
    # Setup mock client for stream_cost_and_usage
    mock_client = AsyncMock()
    mock_results_with_groups = [
        {
            "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
            "Groups": [
                {
                    "Keys": ["Total"],
                    "Metrics": {"AmortizedCost": {"Amount": "15.5", "Unit": "USD"}},
                }
            ],
        }
    ]
    mock_client.get_cost_and_usage.return_value = {
        "ResultsByTime": mock_results_with_groups
    }

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            pass

    aws_adapter.session.client.return_value = AsyncContextManagerMock()

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

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
