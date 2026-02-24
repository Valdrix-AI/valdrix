from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403
from app.modules.enforcement.api.v1.schemas import (
    ActiveReservationItem,
    ReservationReconcileOverdueRequest,
    ReservationReconcileOverdueResponse,
    ReservationReconcileRequest,
    ReservationReconcileResponse,
    ReservationReconciliationExceptionItem,
)
from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.config import get_settings
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


def _reservation_reconcile_sla_seconds() -> int:
    raw = getattr(
        get_settings(),
        "ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS",
        86400,
    )
    try:
        sla_seconds = int(raw)
    except (TypeError, ValueError):
        sla_seconds = 86400
    return max(60, min(sla_seconds, 604800))


@router.get("/reservations/active", response_model=list[ActiveReservationItem])
async def list_active_reservations(
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[ActiveReservationItem]:
    service = EnforcementService(db)
    now = datetime.now(timezone.utc)
    rows = await service.list_active_reservations(
        tenant_id=tenant_or_403(current_user),
        limit=limit,
    )
    return [
        ActiveReservationItem(
            decision_id=item.id,
            source=item.source.value,
            environment=item.environment,
            project_id=item.project_id,
            action=item.action,
            resource_reference=item.resource_reference,
            reason_codes=list(item.reason_codes or []),
            reserved_allocation_usd=item.reserved_allocation_usd,
            reserved_credit_usd=item.reserved_credit_usd,
            reserved_total_usd=item.reserved_allocation_usd + item.reserved_credit_usd,
            created_at=item.created_at,
            age_seconds=max(
                0,
                int(
                    (
                        now
                        - (
                            item.created_at
                            if item.created_at.tzinfo
                            else item.created_at.replace(tzinfo=timezone.utc)
                        )
                    ).total_seconds()
                ),
            ),
        )
        for item in rows
    ]


@router.post(
    "/reservations/{decision_id}/reconcile",
    response_model=ReservationReconcileResponse,
)
async def reconcile_reservation(
    decision_id: UUID,
    payload: ReservationReconcileRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ReservationReconcileResponse:
    service = EnforcementService(db)
    result = await service.reconcile_reservation(
        tenant_id=tenant_or_403(current_user),
        decision_id=decision_id,
        actor_id=current_user.id,
        actual_monthly_delta_usd=payload.actual_monthly_delta_usd,
        notes=payload.notes,
    )
    return ReservationReconcileResponse(
        decision_id=result.decision.id,
        status=result.status,
        released_reserved_usd=result.released_reserved_usd,
        actual_monthly_delta_usd=result.actual_monthly_delta_usd,
        drift_usd=result.drift_usd,
        reservation_active=bool(result.decision.reservation_active),
        reconciled_at=result.reconciled_at,
    )


@router.post(
    "/reservations/reconcile-overdue",
    response_model=ReservationReconcileOverdueResponse,
)
async def reconcile_overdue_reservations(
    payload: ReservationReconcileOverdueRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ReservationReconcileOverdueResponse:
    service = EnforcementService(db)
    summary = await service.reconcile_overdue_reservations(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        older_than_seconds=(
            payload.older_than_seconds
            if payload.older_than_seconds is not None
            else _reservation_reconcile_sla_seconds()
        ),
        limit=payload.limit,
    )
    return ReservationReconcileOverdueResponse(
        released_count=summary.released_count,
        total_released_usd=summary.total_released_usd,
        decision_ids=summary.decision_ids,
        older_than_seconds=summary.older_than_seconds,
    )


@router.get(
    "/reservations/reconciliation-exceptions",
    response_model=list[ReservationReconciliationExceptionItem],
)
async def list_reconciliation_exceptions(
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[ReservationReconciliationExceptionItem]:
    service = EnforcementService(db)
    rows = await service.list_reconciliation_exceptions(
        tenant_id=tenant_or_403(current_user),
        limit=limit,
    )
    return [
        ReservationReconciliationExceptionItem(
            decision_id=item.decision.id,
            source=item.decision.source.value,
            environment=item.decision.environment,
            project_id=item.decision.project_id,
            action=item.decision.action,
            resource_reference=item.decision.resource_reference,
            expected_reserved_usd=item.expected_reserved_usd,
            actual_monthly_delta_usd=item.actual_monthly_delta_usd,
            drift_usd=item.drift_usd,
            status=item.status,
            reconciled_at=item.reconciled_at,
            notes=item.notes,
        )
        for item in rows
    ]
