from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Callable, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import SQLAlchemyError

from app.models.enforcement import EnforcementApprovalRequest, EnforcementDecision


async def reconcile_reservation(
    *,
    service: Any,
    tenant_id: UUID,
    decision_id: UUID,
    actor_id: UUID,
    actual_monthly_delta_usd: Decimal,
    notes: str | None,
    idempotency_key: str | None,
    reservation_reconciliation_result_cls: type[Any],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    unique_reason_codes_fn: Callable[[list[str]], list[str]],
    utcnow_fn: Callable[[], Any],
    reservation_reconciliations_total_metric: Any,
    reservation_drift_usd_total_metric: Any,
) -> Any:
    decision = (
        await service.db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == decision_id)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    actual = quantize_fn(to_decimal_fn(actual_monthly_delta_usd), "0.0001")
    if actual < Decimal("0"):
        raise HTTPException(
            status_code=422,
            detail="actual_monthly_delta_usd must be >= 0",
        )
    normalized_notes = (str(notes).strip() if notes else None) or None
    normalized_idempotency_key = (str(idempotency_key).strip() if idempotency_key else None) or None

    if not decision.reservation_active:
        replay = service._build_reservation_reconciliation_idempotent_replay(
            decision=decision,
            actual_monthly_delta_usd=actual,
            notes=normalized_notes,
            idempotency_key=normalized_idempotency_key,
        )
        if replay is not None:
            reservation_reconciliations_total_metric.labels(
                trigger="manual_replay",
                status=replay.status,
            ).inc()
            return replay
        raise HTTPException(status_code=409, detail="Reservation is not active")

    # Claim active reservation atomically to prevent double-settlement when
    # concurrent workers race and row-level locks are unavailable/degraded.
    claim = cast(
        CursorResult[Any],
        await service.db.execute(
            update(EnforcementDecision)
            .where(EnforcementDecision.id == decision_id)
            .where(EnforcementDecision.tenant_id == tenant_id)
            .where(EnforcementDecision.reservation_active.is_(True))
            .values(reservation_active=False)
        ),
    )
    claimed_rows = int(claim.rowcount or 0)
    if claimed_rows != 1:
        await service.db.rollback()
        refreshed = (
            await service.db.execute(
                select(EnforcementDecision)
                .where(EnforcementDecision.id == decision_id)
                .where(EnforcementDecision.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        replay = service._build_reservation_reconciliation_idempotent_replay(
            decision=refreshed,
            actual_monthly_delta_usd=actual,
            notes=normalized_notes,
            idempotency_key=normalized_idempotency_key,
        )
        if replay is not None:
            reservation_reconciliations_total_metric.labels(
                trigger="manual_replay",
                status=replay.status,
            ).inc()
            return replay
        raise HTTPException(status_code=409, detail="Reservation is not active")
    decision.reservation_active = False

    try:
        now = utcnow_fn()
        reserved_allocation = quantize_fn(
            to_decimal_fn(decision.reserved_allocation_usd),
            "0.0001",
        )
        reserved_credit = quantize_fn(
            to_decimal_fn(decision.reserved_credit_usd),
            "0.0001",
        )
        credit_needed = max(Decimal("0.0000"), actual - reserved_allocation)
        consumed_credit = quantize_fn(min(reserved_credit, credit_needed), "0.0001")
        released_credit = quantize_fn(reserved_credit - consumed_credit, "0.0001")
        credit_settlement = await service._settle_credit_reservations_for_decision(
            tenant_id=tenant_id,
            decision=decision,
            consumed_credit_usd=consumed_credit,
            now=now,
        )

        released_total = quantize_fn(
            reserved_allocation + reserved_credit,
            "0.0001",
        )
        drift = quantize_fn(actual - released_total, "0.0001")
        status = (
            "matched"
            if drift == Decimal("0.0000")
            else ("overage" if drift > Decimal("0") else "savings")
        )

        reasons = list(decision.reason_codes or [])
        reasons.append("reservation_reconciled")
        if drift != Decimal("0.0000"):
            reasons.append("reservation_reconciliation_drift")
        decision.reason_codes = unique_reason_codes_fn(reasons)
        decision.reserved_allocation_usd = Decimal("0")
        decision.reserved_credit_usd = Decimal("0")
        decision.response_payload = {
            **(decision.response_payload or {}),
            "reservation_reconciliation": {
                "reconciled_at": now.isoformat(),
                "reconciled_by_user_id": str(actor_id),
                "expected_reserved_usd": str(released_total),
                "actual_monthly_delta_usd": str(actual),
                "drift_usd": str(drift),
                "status": status,
                "notes": normalized_notes,
                "idempotency_key": normalized_idempotency_key,
                "credit_reserved_usd": str(reserved_credit),
                "credit_consumed_usd": str(consumed_credit),
                "credit_released_usd": str(released_credit),
                "credit_settlement": credit_settlement,
            },
        }
        approval = await service._get_approval_by_decision(decision.id)
        service._append_decision_ledger_entry(
            decision_row=decision,
            approval_row=approval,
        )

        await service.db.commit()
    except (
        HTTPException,
        SQLAlchemyError,
        ArithmeticError,
        ValueError,
        TypeError,
        RuntimeError,
    ):
        await service.db.rollback()
        raise
    reservation_reconciliations_total_metric.labels(
        trigger="manual",
        status=status,
    ).inc()
    if drift > Decimal("0.0000"):
        reservation_drift_usd_total_metric.labels(direction="overage").inc(float(drift))
    elif drift < Decimal("0.0000"):
        reservation_drift_usd_total_metric.labels(direction="savings").inc(
            float(abs(drift))
        )
    await service.db.refresh(decision)
    return reservation_reconciliation_result_cls(
        decision=decision,
        released_reserved_usd=released_total,
        actual_monthly_delta_usd=actual,
        drift_usd=drift,
        status=status,
        reconciled_at=now,
    )


async def reconcile_overdue_reservations(
    *,
    service: Any,
    tenant_id: UUID,
    actor_id: UUID,
    older_than_seconds: int,
    limit: int,
    overdue_reservation_reconciliation_result_cls: type[Any],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    unique_reason_codes_fn: Callable[[list[str]], list[str]],
    utcnow_fn: Callable[[], Any],
    reservation_reconciliations_total_metric: Any,
) -> Any:
    bounded_age = max(60, min(int(older_than_seconds), 604800))
    bounded_limit = max(1, min(int(limit), 1000))
    now = utcnow_fn()
    cutoff = now - timedelta(seconds=bounded_age)

    rows = await service.db.execute(
        select(EnforcementDecision)
        .where(EnforcementDecision.tenant_id == tenant_id)
        .where(EnforcementDecision.reservation_active.is_(True))
        .where(EnforcementDecision.created_at < cutoff)
        .order_by(EnforcementDecision.created_at.asc())
        .limit(bounded_limit)
        .with_for_update(skip_locked=True)
    )
    decisions = list(rows.scalars().all())
    if not decisions:
        return overdue_reservation_reconciliation_result_cls(
            released_count=0,
            total_released_usd=Decimal("0.0000"),
            decision_ids=[],
            older_than_seconds=bounded_age,
        )
    approval_rows = (
        await service.db.execute(
            select(EnforcementApprovalRequest).where(
                EnforcementApprovalRequest.decision_id.in_([decision.id for decision in decisions])
            )
        )
    ).scalars().all()
    approval_by_decision: dict[UUID, EnforcementApprovalRequest] = {
        approval.decision_id: approval for approval in approval_rows
    }

    total_released = Decimal("0.0000")
    decision_ids: list[UUID] = []
    try:
        for decision in decisions:
            claim = cast(
                CursorResult[Any],
                await service.db.execute(
                    update(EnforcementDecision)
                    .where(EnforcementDecision.id == decision.id)
                    .where(EnforcementDecision.tenant_id == tenant_id)
                    .where(EnforcementDecision.reservation_active.is_(True))
                    .values(reservation_active=False)
                ),
            )
            if int(claim.rowcount or 0) != 1:
                continue
            decision.reservation_active = False

            released = quantize_fn(
                to_decimal_fn(decision.reserved_allocation_usd)
                + to_decimal_fn(decision.reserved_credit_usd),
                "0.0001",
            )
            credit_settlement = await service._settle_credit_reservations_for_decision(
                tenant_id=tenant_id,
                decision=decision,
                consumed_credit_usd=Decimal("0"),
                now=now,
            )
            total_released = quantize_fn(total_released + released, "0.0001")
            decision_ids.append(decision.id)

            reasons = list(decision.reason_codes or [])
            reasons.append("reservation_auto_released_sla")
            decision.reason_codes = unique_reason_codes_fn(reasons)
            decision.reserved_allocation_usd = Decimal("0")
            decision.reserved_credit_usd = Decimal("0")
            decision.response_payload = {
                **(decision.response_payload or {}),
                "auto_reconciliation": {
                    "released_at": now.isoformat(),
                    "released_by_user_id": str(actor_id),
                    "released_reserved_usd": str(released),
                    "older_than_seconds": bounded_age,
                    "reason": "reservation_reconciliation_sla_expired",
                    "credit_settlement": credit_settlement,
                },
            }
            service._append_decision_ledger_entry(
                decision_row=decision,
                approval_row=approval_by_decision.get(decision.id),
            )
    except (
        HTTPException,
        SQLAlchemyError,
        ArithmeticError,
        ValueError,
        TypeError,
        RuntimeError,
    ):
        await service.db.rollback()
        raise

    if not decision_ids:
        return overdue_reservation_reconciliation_result_cls(
            released_count=0,
            total_released_usd=Decimal("0.0000"),
            decision_ids=[],
            older_than_seconds=bounded_age,
        )

    await service.db.commit()
    reservation_reconciliations_total_metric.labels(
        trigger="auto",
        status="auto_release",
    ).inc(len(decision_ids))
    return overdue_reservation_reconciliation_result_cls(
        released_count=len(decision_ids),
        total_released_usd=total_released,
        decision_ids=decision_ids,
        older_than_seconds=bounded_age,
    )
