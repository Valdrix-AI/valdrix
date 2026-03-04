from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementCreditGrant,
    EnforcementCreditPoolType,
    EnforcementCreditReservationAllocation,
    EnforcementDecision,
)


async def get_credit_headrooms(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    scope_key: str,
    now: datetime,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    as_utc_fn: Callable[[datetime], datetime],
) -> tuple[Decimal, Decimal]:
    normalized_scope = str(scope_key or "default").strip().lower() or "default"
    reserved_remaining = (
        await db.execute(
            select(func.coalesce(func.sum(EnforcementCreditGrant.remaining_amount_usd), 0))
            .where(EnforcementCreditGrant.tenant_id == tenant_id)
            .where(EnforcementCreditGrant.pool_type == EnforcementCreditPoolType.RESERVED)
            .where(EnforcementCreditGrant.active.is_(True))
            .where(
                EnforcementCreditGrant.scope_key.in_(
                    [normalized_scope, "default"]
                )
            )
            .where(
                or_(
                    EnforcementCreditGrant.expires_at.is_(None),
                    EnforcementCreditGrant.expires_at > now,
                )
            )
        )
    ).scalar_one()
    emergency_remaining = (
        await db.execute(
            select(func.coalesce(func.sum(EnforcementCreditGrant.remaining_amount_usd), 0))
            .where(EnforcementCreditGrant.tenant_id == tenant_id)
            .where(EnforcementCreditGrant.pool_type == EnforcementCreditPoolType.EMERGENCY)
            .where(EnforcementCreditGrant.active.is_(True))
            .where(
                or_(
                    EnforcementCreditGrant.expires_at.is_(None),
                    EnforcementCreditGrant.expires_at > now,
                )
            )
        )
    ).scalar_one()

    decisions_reserved_total = (
        await db.execute(
            select(func.coalesce(func.sum(EnforcementDecision.reserved_credit_usd), 0))
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(True))
        )
    ).scalar_one()
    mapped_active_total = (
        await db.execute(
            select(
                func.coalesce(
                    func.sum(
                        EnforcementCreditReservationAllocation.reserved_amount_usd
                    ),
                    0,
                )
            )
            .where(EnforcementCreditReservationAllocation.tenant_id == tenant_id)
            .where(EnforcementCreditReservationAllocation.active.is_(True))
        )
    ).scalar_one()

    uncovered_legacy_reserved = max(
        Decimal("0"),
        to_decimal_fn(decisions_reserved_total) - to_decimal_fn(mapped_active_total),
    )

    reserved_headroom = max(Decimal("0"), to_decimal_fn(reserved_remaining))
    emergency_headroom = max(Decimal("0"), to_decimal_fn(emergency_remaining))
    if uncovered_legacy_reserved > Decimal("0"):
        reserved_reduction = min(uncovered_legacy_reserved, reserved_headroom)
        reserved_headroom = quantize_fn(
            max(Decimal("0"), reserved_headroom - reserved_reduction),
            "0.0001",
        )
        remaining_uncovered = quantize_fn(
            uncovered_legacy_reserved - reserved_reduction,
            "0.0001",
        )
        if remaining_uncovered > Decimal("0"):
            emergency_headroom = quantize_fn(
                max(Decimal("0"), emergency_headroom - remaining_uncovered),
                "0.0001",
            )

    return (
        quantize_fn(reserved_headroom, "0.0001"),
        quantize_fn(emergency_headroom, "0.0001"),
    )


async def reserve_credit_for_decision(
    *,
    tenant_id: UUID,
    decision_id: UUID,
    scope_key: str,
    reserve_reserved_credit_usd: Decimal,
    reserve_emergency_credit_usd: Decimal,
    now: datetime,
    reserve_credit_from_grants_fn: Callable[..., Awaitable[list[dict[str, str]]]],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
) -> list[dict[str, str]]:
    reserved_target = quantize_fn(to_decimal_fn(reserve_reserved_credit_usd), "0.0001")
    emergency_target = quantize_fn(to_decimal_fn(reserve_emergency_credit_usd), "0.0001")
    normalized_scope = str(scope_key or "default").strip().lower() or "default"
    allocations: list[dict[str, str]] = []
    if reserved_target > Decimal("0.0000"):
        allocations.extend(
            await reserve_credit_from_grants_fn(
                tenant_id=tenant_id,
                decision_id=decision_id,
                scope_key=normalized_scope,
                pool_type=EnforcementCreditPoolType.RESERVED,
                reserve_target_usd=reserved_target,
                now=now,
            )
        )
    if emergency_target > Decimal("0.0000"):
        allocations.extend(
            await reserve_credit_from_grants_fn(
                tenant_id=tenant_id,
                decision_id=decision_id,
                scope_key=normalized_scope,
                pool_type=EnforcementCreditPoolType.EMERGENCY,
                reserve_target_usd=emergency_target,
                now=now,
            )
        )

    return allocations


async def reserve_credit_from_grants(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    decision_id: UUID,
    scope_key: str,
    pool_type: EnforcementCreditPoolType,
    reserve_target_usd: Decimal,
    now: datetime,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
) -> list[dict[str, str]]:
    target = quantize_fn(to_decimal_fn(reserve_target_usd), "0.0001")
    if target <= Decimal("0.0000"):
        return []

    scope_priority = case(
        (EnforcementCreditGrant.scope_key == scope_key, 0),
        (EnforcementCreditGrant.scope_key == "default", 1),
        else_=2,
    )
    query = (
        select(EnforcementCreditGrant)
        .where(EnforcementCreditGrant.tenant_id == tenant_id)
        .where(EnforcementCreditGrant.active.is_(True))
        .where(EnforcementCreditGrant.pool_type == pool_type)
        .where(
            or_(
                EnforcementCreditGrant.expires_at.is_(None),
                EnforcementCreditGrant.expires_at > now,
            )
        )
        .with_for_update()
    )
    if pool_type == EnforcementCreditPoolType.RESERVED:
        query = query.where(EnforcementCreditGrant.scope_key.in_([scope_key, "default"]))
        query = query.order_by(
            scope_priority.asc(),
            case((EnforcementCreditGrant.expires_at.is_(None), 1), else_=0).asc(),
            EnforcementCreditGrant.expires_at.asc(),
            EnforcementCreditGrant.created_at.asc(),
            EnforcementCreditGrant.id.asc(),
        )
    else:
        query = query.order_by(
            case((EnforcementCreditGrant.expires_at.is_(None), 1), else_=0).asc(),
            EnforcementCreditGrant.expires_at.asc(),
            EnforcementCreditGrant.created_at.asc(),
            EnforcementCreditGrant.id.asc(),
        )

    rows = await db.execute(query)
    grants = list(rows.scalars().all())

    remaining = target
    allocations: list[dict[str, str]] = []
    for grant in grants:
        if remaining <= Decimal("0.0000"):
            break

        grant_remaining = quantize_fn(to_decimal_fn(grant.remaining_amount_usd), "0.0001")
        if grant_remaining <= Decimal("0.0000"):
            continue

        reserve_amount = quantize_fn(min(remaining, grant_remaining), "0.0001")
        if reserve_amount <= Decimal("0.0000"):
            continue

        grant.remaining_amount_usd = quantize_fn(grant_remaining - reserve_amount, "0.0001")
        if to_decimal_fn(grant.remaining_amount_usd) <= Decimal("0.0000"):
            grant.active = False

        db.add(
            EnforcementCreditReservationAllocation(
                tenant_id=tenant_id,
                decision_id=decision_id,
                credit_grant_id=grant.id,
                credit_pool_type=pool_type,
                reserved_amount_usd=reserve_amount,
                consumed_amount_usd=Decimal("0"),
                released_amount_usd=Decimal("0"),
                active=True,
            )
        )
        allocations.append(
            {
                "credit_grant_id": str(grant.id),
                "credit_pool_type": pool_type.value,
                "scope_key": str(grant.scope_key),
                "reserved_amount_usd": str(reserve_amount),
            }
        )
        remaining = quantize_fn(remaining - reserve_amount, "0.0001")

    if remaining > Decimal("0.0000"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Insufficient credit grant headroom during reservation allocation "
                f"(pool={pool_type.value}, missing={remaining})"
            ),
        )

    return allocations


async def settle_credit_reservations_for_decision(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    decision: EnforcementDecision,
    consumed_credit_usd: Decimal,
    now: datetime,
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    as_utc_fn: Callable[[datetime], datetime],
) -> list[dict[str, str]]:
    reserved_credit = quantize_fn(to_decimal_fn(decision.reserved_credit_usd), "0.0001")
    if reserved_credit <= Decimal("0.0000"):
        return []

    bounded_consumed = quantize_fn(
        min(max(Decimal("0.0000"), to_decimal_fn(consumed_credit_usd)), reserved_credit),
        "0.0001",
    )
    remaining_consume = bounded_consumed
    remaining_release = quantize_fn(reserved_credit - bounded_consumed, "0.0001")

    allocation_rows = await db.execute(
        select(EnforcementCreditReservationAllocation)
        .where(EnforcementCreditReservationAllocation.tenant_id == tenant_id)
        .where(EnforcementCreditReservationAllocation.decision_id == decision.id)
        .where(EnforcementCreditReservationAllocation.active.is_(True))
        .order_by(EnforcementCreditReservationAllocation.created_at.asc())
        .with_for_update()
    )
    allocations = list(allocation_rows.scalars().all())
    if not allocations:
        raise HTTPException(
            status_code=409,
            detail="Missing credit reservation allocation rows for decision settlement",
        )

    grant_ids = sorted({allocation.credit_grant_id for allocation in allocations})
    grant_rows = await db.execute(
        select(EnforcementCreditGrant)
        .where(EnforcementCreditGrant.tenant_id == tenant_id)
        .where(EnforcementCreditGrant.id.in_(grant_ids))
        .with_for_update()
    )
    grants_by_id = {grant.id: grant for grant in grant_rows.scalars().all()}

    diagnostics: list[dict[str, str]] = []
    for allocation in allocations:
        grant = grants_by_id.get(allocation.credit_grant_id)
        if grant is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Missing credit grant row for reservation allocation "
                    f"{allocation.id}"
                ),
            )

        reserved_amount = quantize_fn(
            to_decimal_fn(allocation.reserved_amount_usd),
            "0.0001",
        )
        consume_amount = quantize_fn(
            min(reserved_amount, remaining_consume),
            "0.0001",
        )
        remaining_consume = quantize_fn(remaining_consume - consume_amount, "0.0001")

        release_amount = quantize_fn(reserved_amount - consume_amount, "0.0001")
        if release_amount > remaining_release:
            release_amount = remaining_release
        remaining_release = quantize_fn(remaining_release - release_amount, "0.0001")

        if release_amount > Decimal("0.0000"):
            new_remaining = quantize_fn(
                to_decimal_fn(grant.remaining_amount_usd) + release_amount,
                "0.0001",
            )
            grant_total = quantize_fn(to_decimal_fn(grant.total_amount_usd), "0.0001")
            if new_remaining > grant_total:
                new_remaining = grant_total
            grant.remaining_amount_usd = new_remaining

        grant_active = to_decimal_fn(grant.remaining_amount_usd) > Decimal("0.0000")
        not_expired = grant.expires_at is None or as_utc_fn(grant.expires_at) > now
        grant.active = bool(grant_active and not_expired)

        allocation.consumed_amount_usd = quantize_fn(
            to_decimal_fn(allocation.consumed_amount_usd) + consume_amount,
            "0.0001",
        )
        allocation.released_amount_usd = quantize_fn(
            to_decimal_fn(allocation.released_amount_usd) + release_amount,
            "0.0001",
        )
        allocation.active = False
        allocation.settled_at = now

        diagnostics.append(
            {
                "credit_grant_id": str(grant.id),
                "credit_pool_type": allocation.credit_pool_type.value,
                "scope_key": str(grant.scope_key),
                "reserved_amount_usd": str(reserved_amount),
                "consumed_amount_usd": str(consume_amount),
                "released_amount_usd": str(release_amount),
                "grant_remaining_amount_usd_after": str(
                    quantize_fn(to_decimal_fn(grant.remaining_amount_usd), "0.0001")
                ),
            }
        )

    if remaining_consume > Decimal("0.0000") or remaining_release > Decimal("0.0000"):
        raise HTTPException(
            status_code=409,
            detail=(
                "Credit reservation settlement drift detected "
                f"(remaining_consume={remaining_consume}, "
                f"remaining_release={remaining_release})"
            ),
        )

    return diagnostics
