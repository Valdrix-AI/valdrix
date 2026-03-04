import pytest
from unittest.mock import patch
import sys
import types

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
    ) as mock_hourly:
        waste = PricingService.estimate_monthly_waste("aws", "nat_gateway", quantity=3)
        assert waste == pytest.approx(2.0 * 730 * 3)
        assert mock_hourly.call_args.args[3] == "global"


def test_get_hourly_rate_default_region_is_provider_neutral():
    with (
        patch(
            "app.modules.reporting.domain.pricing.service.DEFAULT_RATES",
            {"aws": {"instance": {"default": 1.0}}},
        ),
        patch(
            "app.modules.reporting.domain.pricing.service.REGION_MULTIPLIERS",
            {"us-east-1": 1.25},
        ),
    ):
        # Without an explicit region, pricing should not implicitly apply AWS us-east-1 multiplier.
        rate = PricingService.get_hourly_rate("aws", "instance")
        assert rate == pytest.approx(1.0)


def test_sync_with_aws_handles_recoverable_botocore_errors():
    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    class FakeClient:
        def get_products(self, **kwargs):
            raise FakeClientError("pricing endpoint unavailable")

    fake_boto3 = types.SimpleNamespace(
        client=lambda service_name, region_name: FakeClient()
    )
    fake_botocore_exceptions = types.SimpleNamespace(
        BotoCoreError=FakeBotoCoreError,
        ClientError=FakeClientError,
    )

    with (
        patch.dict(
            sys.modules,
            {
                "boto3": fake_boto3,
                "botocore.exceptions": fake_botocore_exceptions,
            },
        ),
        patch("app.modules.reporting.domain.pricing.service.logger") as logger_mock,
    ):
        PricingService.sync_with_aws()

    logger_mock.error.assert_called_once()


def test_sync_with_aws_does_not_swallow_base_exceptions():
    class FakeBotoCoreError(Exception):
        pass

    class FakeClientError(Exception):
        pass

    class FatalClient:
        def get_products(self, **kwargs):
            raise KeyboardInterrupt("stop")

    fake_boto3 = types.SimpleNamespace(
        client=lambda service_name, region_name: FatalClient()
    )
    fake_botocore_exceptions = types.SimpleNamespace(
        BotoCoreError=FakeBotoCoreError,
        ClientError=FakeClientError,
    )

    with patch.dict(
        sys.modules,
        {
            "boto3": fake_boto3,
            "botocore.exceptions": fake_botocore_exceptions,
        },
    ):
        with pytest.raises(KeyboardInterrupt, match="stop"):
            PricingService.sync_with_aws()
