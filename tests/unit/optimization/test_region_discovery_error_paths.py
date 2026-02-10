import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from botocore.exceptions import ClientError

from app.modules.optimization.adapters.aws.region_discovery import RegionDiscovery


@pytest.mark.asyncio
async def test_region_discovery_invalid_credentials_type_fallback():
    rd = RegionDiscovery(credentials="not-a-dict")
    regions = await rd.get_enabled_regions()
    assert regions == rd._get_fallback_regions()


@pytest.mark.asyncio
async def test_region_discovery_empty_response_fallback():
    mock_ec2 = AsyncMock()
    mock_ec2.describe_regions.return_value = {"Regions": []}

    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    with patch("app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session", return_value=mock_session):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        regions = await rd.get_enabled_regions()

    assert regions == rd._get_fallback_regions()


@pytest.mark.asyncio
async def test_hot_region_invalid_days_falls_back_to_enabled():
    rd = RegionDiscovery()
    with patch.object(rd, "get_enabled_regions", AsyncMock(return_value=["us-east-1"])) as mock_enabled:
        regions = await rd.get_hot_regions(days=0)

    assert regions == ["us-east-1"]
    mock_enabled.assert_awaited_once()


@pytest.mark.asyncio
async def test_hot_region_empty_dimension_values_fallback():
    mock_ce = AsyncMock()
    mock_ce.get_dimension_values.return_value = {"DimensionValues": []}

    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ce

    with patch("app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session", return_value=mock_session):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        with patch.object(rd, "get_enabled_regions", AsyncMock(return_value=["us-west-2"])) as mock_enabled:
            regions = await rd.get_hot_regions(days=30)

    assert regions == ["us-west-2"]
    mock_enabled.assert_awaited_once()


def test_build_client_kwargs_missing_keys_returns_none():
    rd = RegionDiscovery(credentials={"AccessKeyId": "ak"})
    assert rd._build_client_kwargs("enabled_regions") is None


@pytest.mark.asyncio
async def test_enabled_regions_uses_cache_without_session():
    rd = RegionDiscovery()
    rd._cached_enabled_regions = ["us-east-1", "us-west-2"]
    rd.session = MagicMock()
    rd.session.client.side_effect = AssertionError("should not call session when cached")

    regions = await rd.get_enabled_regions()
    assert regions == ["us-east-1", "us-west-2"]


@pytest.mark.asyncio
async def test_hot_regions_uses_cache_without_session():
    rd = RegionDiscovery()
    rd._cached_hot_regions = ["eu-west-1"]
    rd.session = MagicMock()
    rd.session.client.side_effect = AssertionError("should not call session when cached")

    regions = await rd.get_hot_regions()
    assert regions == ["eu-west-1"]


@pytest.mark.asyncio
async def test_enabled_regions_client_error_fallback():
    mock_ec2 = AsyncMock()
    mock_ec2.describe_regions.side_effect = ClientError(
        error_response={"Error": {"Code": "AuthFailure", "Message": "denied"}},
        operation_name="DescribeRegions"
    )
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2

    with patch("app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session", return_value=mock_session):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        regions = await rd.get_enabled_regions()

    assert regions == rd._get_fallback_regions()


@pytest.mark.asyncio
async def test_hot_regions_client_error_fallback():
    mock_ce = AsyncMock()
    mock_ce.get_dimension_values.side_effect = ClientError(
        error_response={"Error": {"Code": "AccessDenied", "Message": "denied"}},
        operation_name="GetDimensionValues"
    )
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ce

    with patch("app.modules.optimization.adapters.aws.region_discovery.aioboto3.Session", return_value=mock_session):
        rd = RegionDiscovery(credentials={"AccessKeyId": "ak", "SecretAccessKey": "sk"})
        with patch.object(rd, "get_enabled_regions", AsyncMock(return_value=["us-east-1"])) as mock_enabled:
            regions = await rd.get_hot_regions(days=7)

    assert regions == ["us-east-1"]
    mock_enabled.assert_awaited_once()


def test_clear_cache_resets():
    rd = RegionDiscovery()
    rd._cached_enabled_regions = ["us-east-1"]
    rd._cached_hot_regions = ["us-west-2"]
    rd.clear_cache()
    assert rd._cached_enabled_regions == []
    assert rd._cached_hot_regions == []
