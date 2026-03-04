from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementBudgetAllocation,
    EnforcementDecision,
    EnforcementSource,
)


class _HasDb(Protocol):
    db: AsyncSession


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


async def get_decision_by_idempotency(
    self: _HasDb,
    *,
    tenant_id: UUID,
    source: EnforcementSource,
    idempotency_key: str,
) -> EnforcementDecision | None:
    return (
        await self.db.execute(
            select(EnforcementDecision).where(
                EnforcementDecision.tenant_id == tenant_id,
                EnforcementDecision.source == source,
                EnforcementDecision.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


async def get_approval_by_decision(
    self: _HasDb,
    decision_id: UUID,
) -> EnforcementApprovalRequest | None:
    return (
        await self.db.execute(
            select(EnforcementApprovalRequest).where(
                EnforcementApprovalRequest.decision_id == decision_id,
            )
        )
    ).scalar_one_or_none()


async def get_reserved_totals(
    self: _HasDb,
    *,
    tenant_id: UUID,
    month_start: Any,
    month_end: Any,
) -> tuple[Decimal, Decimal]:
    row = (
        await self.db.execute(
            select(
                func.coalesce(func.sum(EnforcementDecision.reserved_allocation_usd), 0),
                func.coalesce(func.sum(EnforcementDecision.reserved_credit_usd), 0),
            )
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(True))
            .where(EnforcementDecision.created_at >= month_start)
            .where(EnforcementDecision.created_at < month_end)
        )
    ).one()
    return _to_decimal(row[0]), _to_decimal(row[1])


async def get_effective_budget(
    self: _HasDb,
    *,
    tenant_id: UUID,
    scope_key: str,
) -> EnforcementBudgetAllocation | None:
    normalized_scope = str(scope_key or "default").strip().lower() or "default"

    scoped = (
        await self.db.execute(
            select(EnforcementBudgetAllocation)
            .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
            .where(EnforcementBudgetAllocation.scope_key == normalized_scope)
            .where(EnforcementBudgetAllocation.active.is_(True))
        )
    ).scalar_one_or_none()
    if scoped is not None:
        return scoped

    fallback = (
        await self.db.execute(
            select(EnforcementBudgetAllocation)
            .where(EnforcementBudgetAllocation.tenant_id == tenant_id)
            .where(EnforcementBudgetAllocation.scope_key == "default")
            .where(EnforcementBudgetAllocation.active.is_(True))
        )
    ).scalar_one_or_none()
    return fallback


async def load_approval_with_decision(
    self: _HasDb,
    *,
    tenant_id: UUID,
    approval_id: UUID,
) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
    approval = (
        await self.db.execute(
            select(EnforcementApprovalRequest)
            .where(EnforcementApprovalRequest.id == approval_id)
            .where(EnforcementApprovalRequest.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")

    decision = (
        await self.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == approval.decision_id)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Approval decision not found")

    return approval, decision


def assert_pending(
    self: _HasDb,  # noqa: ARG001
    approval: EnforcementApprovalRequest,
) -> None:
    if approval.status != EnforcementApprovalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Approval request is already {approval.status.value}",
        )
