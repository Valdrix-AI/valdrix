import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from app.shared.adapters.aws import AWSAdapter
from app.models.aws_connection import AWSConnection
from app.shared.core.credentials import AWSCredentials
from app.shared.core.exceptions import ConfigurationError


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
    MultiTenantAWSAdapter no longer supports direct cost streaming.
    It must fail fast and require CUR-based ingestion.
    """
    adapter = AWSAdapter(
        AWSCredentials(
            account_id=mock_connection.aws_account_id,
            role_arn=mock_connection.role_arn,
            external_id=mock_connection.external_id,
            region=mock_connection.region,
            cur_bucket_name="cur-bucket",
            cur_report_name="cur-report",
            cur_prefix="cur-prefix",
        )
    )

    with pytest.raises(ConfigurationError, match="CUR"):
        async for _ in adapter.stream_cost_and_usage(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ):
            pass
