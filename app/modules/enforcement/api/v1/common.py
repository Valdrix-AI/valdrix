from __future__ import annotations

import inspect
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    is_feature_enabled,
    normalize_tier,
)
from app.models.tenant import Tenant


def tenant_or_403(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return user.tenant_id


async def resolve_effective_tier(
    *,
    user: CurrentUser,
    db: AsyncSession,
) -> PricingTier:
    """Resolve tier from user context with tenant-plan fallback for stale caller payloads."""
    declared_tier = normalize_tier(getattr(user, "tier", PricingTier.FREE))
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id is None:
        return declared_tier

    try:
        query_result = await db.execute(select(Tenant.plan).where(Tenant.id == tenant_id))
        scalar_one_or_none = getattr(query_result, "scalar_one_or_none", None)
        if not callable(scalar_one_or_none):
            return declared_tier
        tenant_plan = scalar_one_or_none()
        if inspect.isawaitable(tenant_plan):
            tenant_plan = await tenant_plan
    except Exception:
        return declared_tier

    if tenant_plan is None:
        return declared_tier
    if isinstance(tenant_plan, PricingTier):
        return tenant_plan
    if isinstance(tenant_plan, str):
        return normalize_tier(tenant_plan)
    return declared_tier


async def require_feature_or_403(
    *,
    user: CurrentUser,
    db: AsyncSession,
    feature: FeatureFlag | str,
) -> PricingTier:
    tier = await resolve_effective_tier(user=user, db=db)
    if is_feature_enabled(tier, feature):
        return tier

    feature_name = feature.value if isinstance(feature, FeatureFlag) else str(feature)
    raise HTTPException(
        status_code=403,
        detail=f"Feature '{feature_name}' requires an upgrade. Current tier: {tier.value}",
    )


async def require_features_or_403(
    *,
    user: CurrentUser,
    db: AsyncSession,
    features: tuple[FeatureFlag | str, ...],
) -> PricingTier:
    tier = await resolve_effective_tier(user=user, db=db)
    missing = [
        feature for feature in features if not is_feature_enabled(tier, feature)
    ]
    if not missing:
        return tier

    if len(missing) == 1:
        feature_name = (
            missing[0].value
            if isinstance(missing[0], FeatureFlag)
            else str(missing[0])
        )
        raise HTTPException(
            status_code=403,
            detail=f"Feature '{feature_name}' requires an upgrade. Current tier: {tier.value}",
        )

    feature_names = [
        item.value if isinstance(item, FeatureFlag) else str(item)
        for item in missing
    ]
    raise HTTPException(
        status_code=403,
        detail=(
            "Features "
            + ", ".join(f"'{name}'" for name in feature_names)
            + f" require an upgrade. Current tier: {tier.value}"
        ),
    )
