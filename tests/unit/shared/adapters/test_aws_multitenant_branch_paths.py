from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ConnectTimeoutError, EndpointConnectionError

from app.shared.adapters import aws_multitenant as aws_mt
from app.shared.core.credentials import AWSCredentials
from app.shared.core.exceptions import ConfigurationError


def _creds(*, region: str = "us-east-1") -> AWSCredentials:
    return AWSCredentials(
        account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ValdricsRole",
        external_id="valdrics-test",
        region=region,
        tenant_id=uuid4(),
    )


def _async_cm(value: object) -> MagicMock:
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _tracer_with_span() -> tuple[MagicMock, MagicMock]:
    tracer = MagicMock()
    span = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = span
    cm.__exit__.return_value = False
    tracer.start_as_current_span.return_value = cm
    return tracer, span


@pytest.mark.asyncio
async def test_with_aws_retry_retries_coroutine_and_logs_before_sleep_in_testing() -> None:
    calls = {"count": 0}

    @aws_mt.with_aws_retry
    async def flaky_call() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            raise ConnectTimeoutError(endpoint_url="https://sts.amazonaws.com")
        return "ok"

    with (
        patch.object(aws_mt, "get_settings", return_value=SimpleNamespace(TESTING=True)),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        result = await flaky_call()

    assert result == "ok"
    assert calls["count"] == 2
    logger_mock.debug.assert_called()


@pytest.mark.asyncio
async def test_with_aws_retry_retries_async_generator_branch() -> None:
    calls = {"count": 0}

    @aws_mt.with_aws_retry
    async def flaky_stream():
        calls["count"] += 1
        if calls["count"] == 1:
            raise EndpointConnectionError(endpoint_url="https://ec2.us-east-1.amazonaws.com")
        yield {"id": "r1"}
        yield {"id": "r2"}

    with patch.object(aws_mt, "get_settings", return_value=SimpleNamespace(TESTING=True)):
        items = [item async for item in flaky_stream()]

    assert calls["count"] == 2
    assert items == [{"id": "r1"}, {"id": "r2"}]


@pytest.mark.asyncio
async def test_verify_connection_rejects_unsupported_region() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds(region="ap-south-1"))
    adapter.get_credentials = AsyncMock()

    with (
        patch.object(
            aws_mt, "get_settings", return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1"])
        ),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        ok = await adapter.verify_connection()

    assert ok is False
    assert adapter.last_error is not None
    assert "Unsupported AWS region" in adapter.last_error
    adapter.get_credentials.assert_not_awaited()
    logger_mock.error.assert_called_once()


@pytest.mark.asyncio
async def test_verify_connection_returns_true_when_credentials_load() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.last_error = "stale"
    adapter.get_credentials = AsyncMock(return_value={"AccessKeyId": "x"})

    with patch.object(
        aws_mt, "get_settings", return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1"])
    ):
        ok = await adapter.verify_connection()

    assert ok is True
    assert adapter.last_error is None
    adapter.get_credentials.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_connection_logs_and_returns_false_on_exception() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.get_credentials = AsyncMock(side_effect=RuntimeError("sts down"))

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1", "us-west-2"]),
        ),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        ok = await adapter.verify_connection()

    assert ok is False
    assert adapter.last_error is not None
    assert "AWS STS role verification failed" in adapter.last_error
    logger_mock.error.assert_called_once_with(
        "verify_connection_failed", provider="aws", error="sts down"
    )


@pytest.mark.asyncio
async def test_get_credentials_returns_cached_temp_credentials_when_not_expired() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    cached = {
        "AccessKeyId": "AKIA...",
        "SecretAccessKey": "secret",
        "SessionToken": "token",
        "Expiration": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    adapter._temp_credentials = cached
    adapter._temp_credentials_expire_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    adapter.session.client = MagicMock()

    out = await adapter.get_credentials()

    assert out is cached
    adapter.session.client.assert_not_called()


@pytest.mark.asyncio
async def test_get_credentials_assume_role_success_caches_and_logs() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    expiration = datetime.now(timezone.utc) + timedelta(hours=1)
    sts_client = AsyncMock()
    sts_client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "AKIA...",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
            "Expiration": expiration,
        }
    }
    adapter.session.client = MagicMock(return_value=_async_cm(sts_client))

    with patch.object(aws_mt, "logger") as logger_mock:
        creds = await adapter.get_credentials()

    assert creds["AccessKeyId"] == "AKIA..."
    assert adapter._temp_credentials is creds
    assert adapter._temp_credentials_expire_at == expiration
    logger_mock.info.assert_called_once()


@pytest.mark.asyncio
async def test_get_credentials_refreshes_when_cached_credentials_expired() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter._temp_credentials = {
        "AccessKeyId": "STALE",
        "SecretAccessKey": "stale",
        "SessionToken": "stale",
        "Expiration": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    adapter._temp_credentials_expire_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    fresh_expiration = datetime.now(timezone.utc) + timedelta(hours=1)
    sts_client = AsyncMock()
    sts_client.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "FRESH",
            "SecretAccessKey": "fresh",
            "SessionToken": "fresh",
            "Expiration": fresh_expiration,
        }
    }
    adapter.session.client = MagicMock(return_value=_async_cm(sts_client))

    creds = await adapter.get_credentials()

    assert creds["AccessKeyId"] == "FRESH"
    sts_client.assume_role.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cost_and_usage_raises_cur_configuration_error() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    now = datetime.now(timezone.utc)
    with pytest.raises(ConfigurationError, match="CUR"):
        await adapter.get_cost_and_usage(now, now)


@pytest.mark.asyncio
async def test_stream_cost_and_usage_raises_cur_configuration_error_on_iteration() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    now = datetime.now(timezone.utc)
    stream = adapter.stream_cost_and_usage(now, now)
    with pytest.raises(ConfigurationError, match="CUR"):
        await anext(stream)


@pytest.mark.asyncio
async def test_discover_resources_returns_empty_for_unsupported_region() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds(region="us-east-1"))
    adapter.last_error = "stale"

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["eu-west-1"]),
        ),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        out = await adapter.discover_resources("eip", region="us-east-1")

    assert out == []
    logger_mock.error.assert_called_once()
    assert adapter.last_error is not None
    assert "allowed region list" in adapter.last_error


@pytest.mark.asyncio
async def test_discover_resources_returns_empty_when_resource_mapping_missing() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.last_error = "stale"
    tracer, span = _tracer_with_span()
    registry = MagicMock()
    registry.get_plugins_for_provider.return_value = []

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1", "us-west-2"]),
        ),
        patch("app.shared.core.tracing.get_tracer", return_value=tracer),
        patch("app.modules.optimization.domain.registry.registry", registry),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        out = await adapter.discover_resources("unknown-resource")

    assert out == []
    span.set_attribute.assert_any_call("resource_type", "unknown-resource")
    logger_mock.warning.assert_called_once_with(
        "plugin_not_found_for_resource", resource_type="unknown-resource"
    )
    assert adapter.last_error is not None
    assert "No AWS optimization plugin mapped" in adapter.last_error


@pytest.mark.asyncio
async def test_discover_resources_returns_empty_when_category_plugin_missing() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.last_error = "stale"
    tracer, _span = _tracer_with_span()
    registry = MagicMock()
    registry.get_plugins_for_provider.return_value = [SimpleNamespace(category="storage")]

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1", "us-west-2"]),
        ),
        patch("app.shared.core.tracing.get_tracer", return_value=tracer),
        patch("app.modules.optimization.domain.registry.registry", registry),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        out = await adapter.discover_resources("eip")

    assert out == []
    logger_mock.warning.assert_called_once_with(
        "plugin_not_found_for_resource", resource_type="eip"
    )
    assert adapter.last_error is not None
    assert "No AWS optimization plugin mapped" in adapter.last_error


@pytest.mark.asyncio
async def test_discover_resources_returns_scan_results_for_matching_plugin() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.last_error = "stale"
    tracer, span = _tracer_with_span()
    plugin = SimpleNamespace(category="network")
    plugin.scan = AsyncMock(return_value=[{"resource_id": "eip-1"}])
    registry = MagicMock()
    registry.get_plugins_for_provider.return_value = [plugin]
    adapter.get_credentials = AsyncMock(return_value={"AccessKeyId": "AKIA..."})

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1", "us-west-2"]),
        ),
        patch("app.shared.core.tracing.get_tracer", return_value=tracer),
        patch("app.modules.optimization.domain.registry.registry", registry),
    ):
        out = await adapter.discover_resources("eip")

    assert out == [{"resource_id": "eip-1"}]
    adapter.get_credentials.assert_awaited_once()
    plugin.scan.assert_awaited_once()
    span.set_attribute.assert_any_call("tenant_id", str(adapter.credentials.tenant_id))
    assert adapter.last_error is None


@pytest.mark.asyncio
async def test_discover_resources_logs_and_returns_empty_on_scan_error() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    adapter.last_error = "stale"
    tracer, _span = _tracer_with_span()
    plugin = SimpleNamespace(category="network")
    plugin.scan = AsyncMock(side_effect=RuntimeError("scan failed"))
    registry = MagicMock()
    registry.get_plugins_for_provider.return_value = [plugin]
    adapter.get_credentials = AsyncMock(return_value={"AccessKeyId": "AKIA..."})

    with (
        patch.object(
            aws_mt,
            "get_settings",
            return_value=SimpleNamespace(AWS_SUPPORTED_REGIONS=["us-east-1", "us-west-2"]),
        ),
        patch("app.shared.core.tracing.get_tracer", return_value=tracer),
        patch("app.modules.optimization.domain.registry.registry", registry),
        patch.object(aws_mt, "logger") as logger_mock,
    ):
        out = await aws_mt.MultiTenantAWSAdapter.discover_resources.__wrapped__(
            adapter, "eip", region="us-west-2"
        )

    assert out == []
    plugin.scan.assert_awaited_once()
    logger_mock.error.assert_called_once_with(
        "resource_discovery_failed",
        resource_type="eip",
        region="us-west-2",
        error="scan failed",
    )
    assert adapter.last_error is not None
    assert "AWS resource discovery failed" in adapter.last_error


@pytest.mark.asyncio
async def test_get_resource_usage_projects_discovered_inventory_rows() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    with patch.object(
        adapter,
        "discover_resources",
        AsyncMock(
            return_value=[
                {"resource_id": "i-123", "region": "us-east-1", "tags": {"env": "prod"}},
                {"resource_id": "i-456", "region": "us-east-1", "tags": {"env": "dev"}},
            ]
        ),
    ) as mock_discover:
        out = await adapter.get_resource_usage("ec2", "i-123")

    assert len(out) == 1
    assert out[0]["provider"] == "aws"
    assert out[0]["resource_id"] == "i-123"
    assert out[0]["usage_amount"] == 1.0
    assert out[0]["usage_unit"] == "resource"
    mock_discover.assert_awaited_once_with("instance")


@pytest.mark.asyncio
async def test_get_resource_usage_returns_empty_for_blank_or_empty_discovery() -> None:
    adapter = aws_mt.MultiTenantAWSAdapter(_creds())
    assert await adapter.get_resource_usage("   ") == []

    with patch.object(adapter, "discover_resources", AsyncMock(return_value=[])):
        assert await adapter.get_resource_usage("ec2") == []
