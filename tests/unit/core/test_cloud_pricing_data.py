from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from app.shared.core.cloud_pricing_data import (
    get_cloud_hourly_rate,
    refresh_cloud_resource_pricing,
    seed_default_cloud_pricing_catalog,
    sync_supported_aws_pricing,
)


@pytest.mark.asyncio
async def test_seed_default_cloud_pricing_catalog_persists_defaults(db) -> None:
    updated = await seed_default_cloud_pricing_catalog(db)
    assert updated > 0

    refreshed = await refresh_cloud_resource_pricing(db)
    assert refreshed > 0
    assert get_cloud_hourly_rate("aws", "instance", "t3.micro", "us-east-1") > 0


@pytest.mark.asyncio
async def test_get_cloud_hourly_rate_applies_multiplier_from_seeded_catalog(db) -> None:
    await seed_default_cloud_pricing_catalog(db)
    await refresh_cloud_resource_pricing(db)

    base = get_cloud_hourly_rate("aws", "instance", "t3.micro", "global")
    eu = get_cloud_hourly_rate("aws", "instance", "t3.micro", "eu-west-1")
    assert eu == pytest.approx(base * 1.10)


@pytest.mark.asyncio
async def test_sync_supported_aws_pricing_persists_supported_probe(db) -> None:
    class FakeClient:
        def get_products(self, **kwargs):
            assert kwargs["ServiceCode"] == "AmazonEC2"
            return {
                "PriceList": [
                    '{"terms":{"OnDemand":{"x":{"priceDimensions":{"y":{"pricePerUnit":{"USD":"0.123"}}}}}}}'
                ]
            }

    updated = await sync_supported_aws_pricing(db, client=FakeClient())
    assert updated == 1

    await refresh_cloud_resource_pricing(db)
    assert get_cloud_hourly_rate("aws", "nat_gateway", region="us-east-1") == pytest.approx(0.123)


@pytest.mark.asyncio
async def test_sync_supported_aws_pricing_returns_zero_without_boto3() -> None:
    with patch.dict(sys.modules, {"boto3": None}):
        updated = await sync_supported_aws_pricing(client=None)
    assert updated == 0
