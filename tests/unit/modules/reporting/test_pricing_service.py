import pytest
from unittest.mock import AsyncMock, patch

from app.modules.reporting.domain.pricing.service import PricingService


def test_get_hourly_rate_with_multiplier():
    with patch(
        "app.modules.reporting.domain.pricing.service.get_cloud_hourly_rate",
        return_value=0.011,
    ):
        rate = PricingService.get_hourly_rate(
            "aws", "instance", "t3.micro", region="us-west-2"
        )
        assert rate == pytest.approx(0.011)


def test_get_hourly_rate_missing_logs():
    with (
        patch(
            "app.modules.reporting.domain.pricing.service.get_cloud_hourly_rate",
            return_value=0.0,
        ),
        patch("app.modules.reporting.domain.pricing.service.logger") as mock_logger,
    ):
        rate = PricingService.get_hourly_rate("aws", "unknown", "x", region="us-east-1")
        assert rate == 0.0
        mock_logger.debug.assert_called()


def test_estimate_monthly_waste_uses_hourly():
    with patch(
        "app.modules.reporting.domain.pricing.service.PricingService.get_hourly_rate",
        return_value=2.0,
    ) as mock_hourly:
        waste = PricingService.estimate_monthly_waste("aws", "nat_gateway", quantity=3)
        assert waste == pytest.approx(2.0 * 730 * 3)
        assert mock_hourly.call_args.args[3] == "global"


def test_get_hourly_rate_default_region_is_provider_neutral():
    with patch(
        "app.modules.reporting.domain.pricing.service.get_cloud_hourly_rate",
        return_value=1.0,
    ):
        rate = PricingService.get_hourly_rate("aws", "instance")
        assert rate == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_sync_with_aws_delegates_to_supported_catalog_sync():
    with patch(
        "app.modules.reporting.domain.pricing.service.sync_supported_aws_pricing",
        new=AsyncMock(return_value=3),
    ) as sync_mock:
        updated = await PricingService.sync_with_aws()
    assert updated == 3
    sync_mock.assert_awaited_once()
