from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.billing.domain.billing.entitlement_policy import (
    normalize_pricing_tier_value,
    sync_tenant_plan,
)
from app.shared.core.pricing import PricingTier


def test_normalize_pricing_tier_value_accepts_enum_and_string() -> None:
    assert normalize_pricing_tier_value(PricingTier.PRO) == PricingTier.PRO.value
    assert normalize_pricing_tier_value(" Growth ") == PricingTier.GROWTH.value


def test_normalize_pricing_tier_value_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="Unsupported pricing tier value"):
        normalize_pricing_tier_value("not-a-tier")


@pytest.mark.asyncio
async def test_sync_tenant_plan_executes_update() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
    tenant_id = uuid4()

    with patch(
        "app.modules.billing.domain.billing.entitlement_policy.clear_tenant_tier_cache"
    ) as cache_clear:
        await sync_tenant_plan(
            db=db,
            tenant_id=tenant_id,
            tier=PricingTier.ENTERPRISE,
            source="test",
        )

    db.execute.assert_awaited_once()
    cache_clear.assert_called_once_with(tenant_id)


@pytest.mark.asyncio
async def test_sync_tenant_plan_raises_on_missing_tenant_row() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=0))

    with pytest.raises(RuntimeError, match="Tenant plan sync failed"):
        await sync_tenant_plan(
            db=db,
            tenant_id=uuid4(),
            tier=PricingTier.STARTER.value,
            source="test",
        )
