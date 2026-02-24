from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403
from app.modules.enforcement.api.v1.schemas import DecisionLedgerItem
from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


@router.get("/ledger", response_model=list[DecisionLedgerItem])
async def list_decision_ledger(
    limit: int = Query(default=200, ge=1, le=1000),
    start_at: datetime | None = Query(default=None),
    end_at: datetime | None = Query(default=None),
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> list[DecisionLedgerItem]:
    service = EnforcementService(db)
    rows = await service.list_decision_ledger(
        tenant_id=tenant_or_403(current_user),
        limit=limit,
        start_at=start_at,
        end_at=end_at,
    )
    return [
        DecisionLedgerItem(
            ledger_id=item.entry.id,
            decision_id=item.entry.decision_id,
            source=item.entry.source.value,
            environment=item.entry.environment,
            project_id=item.entry.project_id,
            action=item.entry.action,
            resource_reference=item.entry.resource_reference,
            decision=item.entry.decision.value,
            reason_codes=list(item.entry.reason_codes or []),
            policy_version=int(item.entry.policy_version),
            request_fingerprint=item.entry.request_fingerprint,
            idempotency_key=item.entry.idempotency_key,
            estimated_monthly_delta_usd=item.entry.estimated_monthly_delta_usd,
            estimated_hourly_delta_usd=item.entry.estimated_hourly_delta_usd,
            reserved_total_usd=item.entry.reserved_total_usd,
            approval_required=bool(item.entry.approval_required),
            request_payload_sha256=item.entry.request_payload_sha256,
            response_payload_sha256=item.entry.response_payload_sha256,
            decision_created_at=item.entry.decision_created_at,
            recorded_at=item.entry.recorded_at,
        )
        for item in rows
    ]
