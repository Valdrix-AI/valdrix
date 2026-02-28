from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.shared.adapters.aws import AWSAdapter
from app.shared.core.credentials import AWSCredentials
from app.shared.core.exceptions import ConfigurationError


@pytest.fixture
def aws_adapter() -> AWSAdapter:
    creds = AWSCredentials(
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/test-role",
        external_id="test-external-id",
        region="us-east-1",
    )
    return AWSAdapter(creds)


@pytest.mark.asyncio
async def test_aws_adapter_verify_connection(aws_adapter: AWSAdapter) -> None:
    with patch.object(
        aws_adapter,
        "get_credentials",
        AsyncMock(
            return_value={
                "AccessKeyId": "AK",
                "SecretAccessKey": "SK",
                "SessionToken": "ST",
                "Expiration": datetime.now(timezone.utc),
            }
        ),
    ):
        assert await aws_adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_aws_adapter_get_cost_and_usage_requires_cur(
    aws_adapter: AWSAdapter,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with pytest.raises(ConfigurationError, match="CUR"):
        await aws_adapter.get_cost_and_usage(start, end)


@pytest.mark.asyncio
async def test_aws_adapter_stream_cost_and_usage_requires_cur(
    aws_adapter: AWSAdapter,
) -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with pytest.raises(ConfigurationError, match="CUR"):
        async for _ in aws_adapter.stream_cost_and_usage(start, end):
            pass


@pytest.mark.asyncio
async def test_aws_adapter_discover_resources_returns_empty_without_plugin(
    aws_adapter: AWSAdapter,
) -> None:
    with patch(
        "app.modules.optimization.domain.registry.registry.get_plugins_for_provider",
        return_value=[],
    ):
        resources = await aws_adapter.discover_resources("ec2")
    assert resources == []


@pytest.mark.asyncio
async def test_aws_adapter_get_resource_usage(aws_adapter: AWSAdapter) -> None:
    with patch.object(
        aws_adapter,
        "discover_resources",
        AsyncMock(return_value=[{"resource_id": "i-123", "region": "us-east-1"}]),
    ):
        usage = await aws_adapter.get_resource_usage("ec2", "i-123")

    assert len(usage) == 1
    assert usage[0]["resource_id"] == "i-123"
    assert usage[0]["usage_unit"] == "resource"
