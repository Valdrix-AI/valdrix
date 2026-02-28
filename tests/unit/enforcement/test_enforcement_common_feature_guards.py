from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.enforcement.api.v1 import common as enforcement_common
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import FeatureFlag, PricingTier


class _Result:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, value) -> None:
        self._value = value

    async def execute(self, _stmt):
        return _Result(self._value)


@pytest.mark.asyncio
async def test_resolve_effective_tier_prefers_tenant_plan_from_db() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="tier@test.local",
        tenant_id=uuid4(),
        tier=PricingTier.FREE,
    )
    tier = await enforcement_common.resolve_effective_tier(
        user=user,
        db=_DB("pro"),
    )
    assert tier == PricingTier.PRO


@pytest.mark.asyncio
async def test_resolve_effective_tier_falls_back_on_non_string_tenant_plan() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="tier-fallback@test.local",
        tenant_id=uuid4(),
        tier=PricingTier.ENTERPRISE,
    )
    tier = await enforcement_common.resolve_effective_tier(
        user=user,
        db=_DB(SimpleNamespace()),
    )
    assert tier == PricingTier.ENTERPRISE


@pytest.mark.asyncio
async def test_require_feature_or_403_allows_enabled_feature() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="feature-ok@test.local",
        tenant_id=uuid4(),
        tier=PricingTier.PRO,
    )
    tier = await enforcement_common.require_feature_or_403(
        user=user,
        db=_DB("pro"),
        feature=FeatureFlag.API_ACCESS,
    )
    assert tier == PricingTier.PRO


@pytest.mark.asyncio
async def test_require_feature_or_403_rejects_missing_feature() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="feature-no@test.local",
        tenant_id=uuid4(),
        tier=PricingTier.FREE,
    )
    with pytest.raises(HTTPException, match="api_access"):
        await enforcement_common.require_feature_or_403(
            user=user,
            db=_DB("free"),
            feature=FeatureFlag.API_ACCESS,
        )


@pytest.mark.asyncio
async def test_require_features_or_403_reports_multiple_missing_features() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="feature-multi@test.local",
        tenant_id=uuid4(),
        tier=PricingTier.FREE,
    )
    with pytest.raises(HTTPException, match="api_access") as exc_info:
        await enforcement_common.require_features_or_403(
            user=user,
            db=_DB("free"),
            features=(FeatureFlag.API_ACCESS, FeatureFlag.POLICY_CONFIGURATION),
        )
    assert "policy_configuration" in str(exc_info.value.detail)
