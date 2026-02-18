import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from botocore.exceptions import ClientError

from app.modules.optimization.adapters.aws.region_discovery import RegionDiscovery


@pytest.mark.asyncio
async def test_get_active_regions_uses_resource_explorer_if_enabled():
    mock_connection = MagicMock()
    mock_explorer = AsyncMock()
    mock_explorer.is_enabled.return_value = True
    mock_explorer.search_resources.return_value = [
        {"region": "us-east-1"},
        {"region": "eu-central-1"},
        {"region": "us-east-1"},  # Duplicate
    ]

    with patch(
        "app.shared.adapters.aws_resource_explorer.AWSResourceExplorerAdapter",
        return_value=mock_explorer,
    ):
        rd = RegionDiscovery(
            credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"},
            connection=mock_connection,
        )
        regions = await rd.get_active_regions()

    assert regions == ["eu-central-1", "us-east-1"]
    assert rd._cached_active_regions == ["eu-central-1", "us-east-1"]


@pytest.mark.asyncio
async def test_get_active_regions_falls_back_to_enabled_if_re2_disabled():
    mock_connection = MagicMock()
    mock_explorer = AsyncMock()
    mock_explorer.is_enabled.return_value = False

    rd = RegionDiscovery(
        credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"},
        connection=mock_connection,
    )
    # Mock get_enabled_regions to avoid actual EC2 call
    rd.get_enabled_regions = AsyncMock(return_value=["us-west-2"])  # type: ignore

    with patch(
        "app.shared.adapters.aws_resource_explorer.AWSResourceExplorerAdapter",
        return_value=mock_explorer,
    ):
        regions = await rd.get_active_regions()

    assert regions == ["us-west-2"]


@pytest.mark.asyncio
async def test_get_active_regions_falls_back_on_error():
    mock_connection = MagicMock()
    mock_explorer = AsyncMock()
    mock_explorer.is_enabled.side_effect = Exception("RE2 Failed")

    rd = RegionDiscovery(
        credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"},
        connection=mock_connection,
    )
    rd.get_enabled_regions = AsyncMock(return_value=["fallback-region"])  # type: ignore

    with patch(
        "app.shared.adapters.aws_resource_explorer.AWSResourceExplorerAdapter",
        return_value=mock_explorer,
    ):
        regions = await rd.get_active_regions()

    assert regions == ["fallback-region"]


@pytest.mark.asyncio
async def test_region_discovery_invalid_credentials_type_fallback():
    rd = RegionDiscovery(credentials="not-a-dict")  # type: ignore
    regions = await rd.get_enabled_regions()
    assert regions == rd._get_fallback_regions()


@pytest.mark.asyncio
async def test_region_discovery_empty_response_fallback():
    mock_ec2 = AsyncMock()
    mock_ec2.describe_regions.return_value = {"Regions": []}

    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    with patch(
        "app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session",
        return_value=mock_session,
    ):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        regions = await rd.get_enabled_regions()

    assert regions == rd._get_fallback_regions()


def test_build_client_kwargs_missing_keys_returns_none():
    rd = RegionDiscovery(credentials={"AccessKeyId": "ak"})
    assert rd._build_client_kwargs("enabled_regions") is None


@pytest.mark.asyncio
async def test_enabled_regions_uses_cache_without_session():
    rd = RegionDiscovery()
    rd._cached_enabled_regions = ["us-east-1", "us-west-2"]
    # We mock the session but it shouldn't be used
    rd.session = MagicMock()
    
    regions = await rd.get_enabled_regions()
    assert regions == ["us-east-1", "us-west-2"]


@pytest.mark.asyncio
async def test_enabled_regions_client_error_fallback():
    mock_ec2 = AsyncMock()
    mock_ec2.describe_regions.side_effect = ClientError(
        error_response={"Error": {"Code": "AuthFailure", "Message": "denied"}},
        operation_name="DescribeRegions",
    )
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    with patch(
        "app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session",
        return_value=mock_session,
    ):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        regions = await rd.get_enabled_regions()

    assert regions == rd._get_fallback_regions()


def test_clear_cache_resets():
    rd = RegionDiscovery()
    rd._cached_enabled_regions = ["us-east-1"]
    rd._cached_active_regions = ["us-west-2"]
    rd.clear_cache()
    assert rd._cached_enabled_regions == []
    assert rd._cached_active_regions == []
