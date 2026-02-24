from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403
from app.modules.enforcement.api.v1.schemas import (
    ApprovalCreateRequest,
    ApprovalQueueItem,
    ApprovalReviewRequest,
    ApprovalReviewResponse,
    ApprovalTokenConsumeRequest,
    ApprovalTokenConsumeResponse,
)
from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


@router.post("/approvals/requests", response_model=ApprovalReviewResponse)
async def create_approval_request(
    payload: ApprovalCreateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalReviewResponse:
    service = EnforcementService(db)
    approval = await service.create_or_get_approval_request(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        decision_id=payload.decision_id,
        notes=payload.notes,
    )
    return ApprovalReviewResponse(
        status=approval.status.value,
        approval_id=approval.id,
        decision_id=approval.decision_id,
        approval_token=None,
        token_expires_at=approval.approval_token_expires_at,
    )


@router.get("/approvals/queue", response_model=list[ApprovalQueueItem])
async def get_approval_queue(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalQueueItem]:
    service = EnforcementService(db)
    rows = await service.list_pending_approvals(
        tenant_id=tenant_or_403(current_user),
        limit=limit,
    )
    return [
        ApprovalQueueItem(
            approval_id=approval.id,
            decision_id=decision.id,
            status=approval.status.value,
            source=decision.source.value,
            environment=decision.environment,
            project_id=decision.project_id,
            action=decision.action,
            resource_reference=decision.resource_reference,
            estimated_monthly_delta_usd=decision.estimated_monthly_delta_usd,
            reason_codes=list(decision.reason_codes or []),
            expires_at=approval.expires_at,
            created_at=approval.created_at,
        )
        for approval, decision in rows
    ]


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalReviewResponse)
async def approve_approval_request(
    approval_id: UUID,
    payload: ApprovalReviewRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalReviewResponse:
    service = EnforcementService(db)
    approval, decision, token, expires_at = await service.approve_request(
        tenant_id=tenant_or_403(current_user),
        approval_id=approval_id,
        reviewer=current_user,
        notes=payload.notes,
    )
    return ApprovalReviewResponse(
        status=approval.status.value,
        approval_id=approval.id,
        decision_id=decision.id,
        approval_token=token,
        token_expires_at=expires_at,
    )


@router.post("/approvals/consume", response_model=ApprovalTokenConsumeResponse)
@rate_limit("120/minute")
async def consume_approval_token(
    request: Request,
    payload: ApprovalTokenConsumeRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalTokenConsumeResponse:
    _ = request
    service = EnforcementService(db)
    approval, decision = await service.consume_approval_token(
        tenant_id=tenant_or_403(current_user),
        approval_token=payload.approval_token,
        actor_id=current_user.id,
        expected_source=payload.expected_source,
        expected_environment=payload.expected_environment,
        expected_request_fingerprint=payload.expected_request_fingerprint,
        expected_resource_reference=payload.expected_resource_reference,
    )
    token_expires_at = approval.approval_token_expires_at or decision.token_expires_at
    if token_expires_at is None:
        raise HTTPException(status_code=409, detail="Approval token expiry is unavailable")

    consumed_at = approval.approval_token_consumed_at
    if consumed_at is None:
        raise HTTPException(status_code=409, detail="Approval token was not consumed")

    return ApprovalTokenConsumeResponse(
        status="consumed",
        approval_id=approval.id,
        decision_id=decision.id,
        source=decision.source.value,
        environment=decision.environment,
        project_id=decision.project_id,
        action=decision.action,
        resource_reference=decision.resource_reference,
        request_fingerprint=decision.request_fingerprint,
        max_monthly_delta_usd=decision.estimated_monthly_delta_usd,
        token_expires_at=token_expires_at,
        consumed_at=consumed_at,
    )


@router.post("/approvals/{approval_id}/deny", response_model=ApprovalReviewResponse)
async def deny_approval_request(
    approval_id: UUID,
    payload: ApprovalReviewRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ApprovalReviewResponse:
    service = EnforcementService(db)
    approval, decision = await service.deny_request(
        tenant_id=tenant_or_403(current_user),
        approval_id=approval_id,
        reviewer=current_user,
        notes=payload.notes,
    )
    return ApprovalReviewResponse(
        status=approval.status.value,
        approval_id=approval.id,
        decision_id=decision.id,
        approval_token=None,
        token_expires_at=None,
    )
