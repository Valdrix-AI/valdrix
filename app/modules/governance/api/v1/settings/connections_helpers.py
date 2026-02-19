"""
Shared policy and tenant-limit helpers for settings connection routers.
"""

from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    get_tier_limit,
    is_feature_enabled,
    normalize_tier,
)

logger = structlog.get_logger()


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=404, detail="Tenant context lost")
    return user.tenant_id


def _enforce_growth_tier(current_plan: PricingTier, user: CurrentUser) -> None:
    allowed_plans = {PricingTier.GROWTH, PricingTier.PRO, PricingTier.ENTERPRISE}

    if current_plan not in allowed_plans:
        logger.warning(
            "tier_gate_denied",
            tenant_id=str(user.tenant_id),
            plan=current_plan.value,
            required="growth",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Multi-cloud support requires 'Growth' plan or higher. "
                f"Current plan: {current_plan.value}"
            ),
        )


def check_growth_tier(user: CurrentUser) -> PricingTier:
    """
    Ensure tenant is on growth/pro/enterprise plan.

    Uses request-bound `CurrentUser.tier` to avoid additional DB/cache staleness.
    """
    current_plan = normalize_tier(getattr(user, "tier", PricingTier.FREE))
    _enforce_growth_tier(current_plan, user)
    return current_plan


def check_cloud_plus_tier(user: CurrentUser) -> PricingTier:
    """
    Ensure Cloud+ connectors are available for the current tenant tier.
    """
    current_plan = normalize_tier(getattr(user, "tier", PricingTier.FREE))
    if is_feature_enabled(current_plan, FeatureFlag.CLOUD_PLUS_CONNECTORS):
        return current_plan

    logger.warning(
        "tier_gate_denied_cloud_plus",
        tenant_id=str(user.tenant_id),
        plan=current_plan.value,
        required_feature=FeatureFlag.CLOUD_PLUS_CONNECTORS.value,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Cloud+ connectors require 'Pro' plan or higher. "
            f"Current plan: {current_plan.value}"
        ),
    )


def check_idp_deep_scan_tier(user: CurrentUser) -> PricingTier:
    """
    Ensure Stage B IdP deep-scan discovery is available for the tenant tier.
    """
    current_plan = normalize_tier(getattr(user, "tier", PricingTier.FREE))
    if is_feature_enabled(current_plan, FeatureFlag.IDP_DEEP_SCAN):
        return current_plan

    logger.warning(
        "tier_gate_denied_idp_deep_scan",
        tenant_id=str(user.tenant_id),
        plan=current_plan.value,
        required_feature=FeatureFlag.IDP_DEEP_SCAN.value,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "IdP deep scan requires 'Pro' plan or higher. "
            f"Current plan: {current_plan.value}"
        ),
    )


async def _enforce_connection_limit(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    plan: PricingTier,
    limit_key: str,
    model: Any,
    label: str,
) -> None:
    """Enforce per-plan connection limits during creation flows."""
    limit_value = get_tier_limit(plan, limit_key)
    if limit_value is None:
        return

    try:
        max_allowed = int(limit_value)
    except (TypeError, ValueError):
        logger.warning(
            "tier_limit_invalid",
            plan=plan.value,
            limit_key=limit_key,
            limit_value=limit_value,
        )
        return

    if max_allowed <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{label} connections are not available on plan '{plan.value}'. "
                "Please upgrade."
            ),
        )

    used = await db.scalar(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    )
    used_count = int(used or 0)
    if used_count >= max_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plan limit reached for {label} connections: {used_count}/{max_allowed}. "
                "Please upgrade to add more."
            ),
        )
