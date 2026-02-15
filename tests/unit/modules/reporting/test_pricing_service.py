import pytest
from unittest.mock import patch

from app.modules.reporting.domain.pricing.service import PricingService


def test_get_hourly_rate_with_multiplier():
    with (
        patch(
            "app.modules.reporting.domain.pricing.service.DEFAULT_RATES",
            {"aws": {"instance": {"t3.micro": 0.01}}},
        ),
        patch(
            "app.modules.reporting.domain.pricing.service.REGION_MULTIPLIERS",
            {"us-east-1": 1.0, "us-west-2": 1.1},
        ),
    ):
        rate = PricingService.get_hourly_rate(
            "aws", "instance", "t3.micro", region="us-west-2"
        )
        assert rate == pytest.approx(0.011)


def test_get_hourly_rate_missing_logs():
    with (
        patch("app.modules.reporting.domain.pricing.service.DEFAULT_RATES", {}),
        patch(
            "app.modules.reporting.domain.pricing.service.REGION_MULTIPLIERS",
            {"us-east-1": 1.0},
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
    ):
        waste = PricingService.estimate_monthly_waste("aws", "nat_gateway", quantity=3)
        assert waste == pytest.approx(2.0 * 730 * 3)
