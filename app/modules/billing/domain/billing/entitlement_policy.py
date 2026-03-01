"""Centralized billing entitlement plan synchronization policy."""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.shared.core.pricing import PricingTier, clear_tenant_tier_cache

logger = structlog.get_logger()


def normalize_pricing_tier_value(tier: str | PricingTier) -> str:
    """Normalize incoming tier values to canonical pricing tier enum values."""
    if isinstance(tier, PricingTier):
        return tier.value

    candidate = str(tier).strip().lower()
    try:
        return PricingTier(candidate).value
    except ValueError as exc:  # pragma: no cover - defensive path
        raise ValueError(f"Unsupported pricing tier value: {tier!r}") from exc


async def sync_tenant_plan(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    tier: str | PricingTier,
    source: str,
) -> None:
    """Apply tenant plan sync from billing outcomes in one validated policy path."""
    normalized_tier = normalize_pricing_tier_value(tier)
    result = await db.execute(
        update(Tenant).where(Tenant.id == tenant_id).values(plan=normalized_tier)
    )

    rowcount = getattr(result, "rowcount", None)
    if isinstance(rowcount, int) and rowcount != 1:
        raise RuntimeError(
            "Tenant plan sync failed due to missing or duplicated tenant row "
            f"(tenant_id={tenant_id}, updated_rows={rowcount})"
        )

    clear_tenant_tier_cache(tenant_id)

    logger.info(
        "billing_entitlement_synced",
        tenant_id=str(tenant_id),
        tier=normalized_tier,
        source=source,
        updated_rows=rowcount,
    )
