import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from app.shared.adapters.aws import AWSAdapter
from app.models.aws_connection import AWSConnection


@pytest.fixture
def mock_connection():
    conn = MagicMock(spec=AWSConnection)
    conn.tenant_id = "test-tenant"
    conn.aws_account_id = "123456789012"
    conn.role_arn = "arn:aws:iam::123456789012:role/test"
    conn.region = "us-east-1"
    conn.external_id = "test"
    return conn


@pytest.mark.asyncio
async def test_aws_adapter_streaming_performance(mock_connection):
    """
    Benchmark AWS cost streaming with 1,000 mock records.
    Requirement: Should handle >1k records/sec in isolation.
    """
    adapter = AWSAdapter(connection=mock_connection)

    # Mock credentials
    adapter.get_credentials = AsyncMock(
        return_value={
            "AccessKeyId": "AK",
            "SecretAccessKey": "SK",
            "SessionToken": "ST",
            "Expiration": datetime.now(timezone.utc),
        }
    )

    # Mocking large dataset response
    mock_group = {
        "Keys": ["AmazonEC2"],
        "Metrics": {"AmortizedCost": {"Amount": "0.01", "Unit": "USD"}},
    }
    mock_response = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
                "Groups": [mock_group] * 1000,  # 1,000 records per page
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.return_value = mock_response

    class AsyncContextManagerMock:
        async def __aenter__(self):
            return mock_client

        async def __aexit__(self, *args):
            pass

    adapter.session.client = MagicMock(return_value=AsyncContextManagerMock())

    start_time = time.perf_counter()

    count = 0
    async for _ in adapter.stream_cost_and_usage(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    ):
        count += 1

    end_time = time.perf_counter()
    duration = end_time - start_time

    throughput = count / duration if duration > 0 else 0
    print(f"\n[Performance] AWS Streaming Throughput: {throughput:.2f} records/sec")

    assert count == 1000
    # Target: >1000 records/sec
    assert throughput > 1000
