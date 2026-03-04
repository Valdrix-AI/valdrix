from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementBudgetAllocation,
    EnforcementCreditGrant,
    EnforcementCreditPoolType,
)
from app.modules.enforcement.domain.service_utils import _as_utc, _quantize, _utcnow


async def list_budgets(
    *,
    db: AsyncSession,
    tenant_id: UUID,
) -> list[EnforcementBudgetAllocation]:
    rows = await db.execute(
        select(EnforcementBudgetAllocation)
        .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
        .order_by(EnforcementBudgetAllocation.scope_key.asc())
    )
    return list(rows.scalars().all())


async def upsert_budget(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    actor_id: UUID,
    scope_key: str,
    monthly_limit_usd: Decimal,
    active: bool,
    quantize_fn: Callable[[Decimal, str], Decimal],
) -> EnforcementBudgetAllocation:
    normalized_scope = str(scope_key or "default").strip().lower() or "default"
    if monthly_limit_usd < Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="monthly_limit_usd must be >= 0",
        )

    budget = (
        await db.execute(
            select(EnforcementBudgetAllocation).where(
                EnforcementBudgetAllocation.tenant_id == tenant_id,
                EnforcementBudgetAllocation.scope_key == normalized_scope,
            )
        )
    ).scalar_one_or_none()

    if budget is None:
        budget = EnforcementBudgetAllocation(
            tenant_id=tenant_id,
            scope_key=normalized_scope,
            monthly_limit_usd=quantize_fn(monthly_limit_usd, "0.0001"),
            active=bool(active),
            created_by_user_id=actor_id,
        )
        db.add(budget)
    else:
        budget.monthly_limit_usd = quantize_fn(monthly_limit_usd, "0.0001")
        budget.active = bool(active)

    await db.commit()
    await db.refresh(budget)
    return budget


async def list_credits(
    *,
    db: AsyncSession,
    tenant_id: UUID,
) -> list[EnforcementCreditGrant]:
    rows = await db.execute(
        select(EnforcementCreditGrant)
        .where(EnforcementCreditGrant.tenant_id == tenant_id)
        .order_by(EnforcementCreditGrant.created_at.desc())
    )
    return list(rows.scalars().all())


async def create_credit_grant(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    actor_id: UUID,
    pool_type: EnforcementCreditPoolType,
    scope_key: str,
    total_amount_usd: Decimal,
    expires_at: datetime | None,
    reason: str | None,
    quantize_fn: Callable[[Decimal, str], Decimal],
    as_utc_fn: Callable[[datetime], datetime],
    utcnow_fn: Callable[[], datetime],
) -> EnforcementCreditGrant:
    normalized_scope = str(scope_key or "default").strip().lower() or "default"
    amount = quantize_fn(total_amount_usd, "0.0001")
    if amount <= Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="total_amount_usd must be > 0",
        )

    normalized_expires_at = as_utc_fn(expires_at) if expires_at is not None else None
    if normalized_expires_at is not None and normalized_expires_at <= utcnow_fn():
        raise HTTPException(
            status_code=422,
            detail="expires_at must be in the future",
        )

    credit = EnforcementCreditGrant(
        tenant_id=tenant_id,
        pool_type=pool_type,
        scope_key=normalized_scope,
        total_amount_usd=amount,
        remaining_amount_usd=amount,
        expires_at=normalized_expires_at,
        reason=(str(reason).strip() if reason else None),
        active=True,
        created_by_user_id=actor_id,
    )
    db.add(credit)
    await db.commit()
    await db.refresh(credit)
    return credit


async def list_budgets_for_service(
    service: Any,
    tenant_id: UUID,
) -> list[EnforcementBudgetAllocation]:
    return await list_budgets(
        db=service.db,
        tenant_id=tenant_id,
    )


async def upsert_budget_for_service(
    service: Any,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    scope_key: str,
    monthly_limit_usd: Decimal,
    active: bool,
) -> EnforcementBudgetAllocation:
    return await upsert_budget(
        db=service.db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key=scope_key,
        monthly_limit_usd=monthly_limit_usd,
        active=active,
        quantize_fn=_quantize,
    )


async def list_credits_for_service(
    service: Any,
    tenant_id: UUID,
) -> list[EnforcementCreditGrant]:
    return await list_credits(
        db=service.db,
        tenant_id=tenant_id,
    )


async def create_credit_grant_for_service(
    service: Any,
    *,
    tenant_id: UUID,
    actor_id: UUID,
    pool_type: EnforcementCreditPoolType = EnforcementCreditPoolType.RESERVED,
    scope_key: str,
    total_amount_usd: Decimal,
    expires_at: datetime | None,
    reason: str | None,
) -> EnforcementCreditGrant:
    return await create_credit_grant(
        db=service.db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        pool_type=pool_type,
        scope_key=scope_key,
        total_amount_usd=total_amount_usd,
        expires_at=expires_at,
        reason=reason,
        quantize_fn=_quantize,
        as_utc_fn=_as_utc,
        utcnow_fn=_utcnow,
    )
