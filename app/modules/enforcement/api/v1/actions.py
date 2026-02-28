from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import EnforcementActionExecution, EnforcementActionStatus
from app.modules.enforcement.api.v1.common import tenant_or_403, require_feature_or_403
from app.modules.enforcement.api.v1.schemas import (
    ActionCancelRequest,
    ActionCompleteRequest,
    ActionCreateRequest,
    ActionExecutionResponse,
    ActionFailRequest,
    ActionLeaseRequest,
)
from app.modules.enforcement.domain.actions import EnforcementActionOrchestrator
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.pricing import FeatureFlag
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db

router = APIRouter(tags=["Enforcement"])


def _to_action_response(action: EnforcementActionExecution) -> ActionExecutionResponse:
    return ActionExecutionResponse(
        action_id=action.id,
        decision_id=action.decision_id,
        approval_request_id=action.approval_request_id,
        action_type=action.action_type,
        target_reference=action.target_reference,
        idempotency_key=action.idempotency_key,
        request_payload=dict(action.request_payload or {}),
        request_payload_sha256=action.request_payload_sha256,
        status=action.status,
        attempt_count=int(action.attempt_count),
        max_attempts=int(action.max_attempts),
        retry_backoff_seconds=int(action.retry_backoff_seconds),
        lease_ttl_seconds=int(action.lease_ttl_seconds),
        next_retry_at=action.next_retry_at,
        locked_by_worker_id=action.locked_by_worker_id,
        lease_expires_at=action.lease_expires_at,
        last_error_code=action.last_error_code,
        last_error_message=action.last_error_message,
        result_payload=(
            dict(action.result_payload)
            if isinstance(action.result_payload, dict)
            else None
        ),
        result_payload_sha256=action.result_payload_sha256,
        started_at=action.started_at,
        completed_at=action.completed_at,
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.post("/actions/requests", response_model=ActionExecutionResponse)
@rate_limit("120/minute")
async def create_action_request(
    request: Request,
    payload: ActionCreateRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.create_action_request(
        tenant_id=tenant_or_403(current_user),
        actor_id=current_user.id,
        decision_id=payload.decision_id,
        action_type=payload.action_type,
        target_reference=payload.target_reference,
        request_payload=payload.request_payload,
        idempotency_key=payload.idempotency_key,
        max_attempts=payload.max_attempts,
        retry_backoff_seconds=payload.retry_backoff_seconds,
        lease_ttl_seconds=payload.lease_ttl_seconds,
    )
    return _to_action_response(action)


@router.get("/actions/requests", response_model=list[ActionExecutionResponse])
@rate_limit("120/minute")
async def list_action_requests(
    request: Request,
    status: EnforcementActionStatus | None = Query(default=None),
    decision_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[ActionExecutionResponse]:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    actions = await service.list_actions(
        tenant_id=tenant_or_403(current_user),
        status=status,
        decision_id=decision_id,
        limit=limit,
    )
    return [_to_action_response(item) for item in actions]


@router.get("/actions/requests/{action_id}", response_model=ActionExecutionResponse)
@rate_limit("120/minute")
async def get_action_request(
    request: Request,
    action_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.get_action(
        tenant_id=tenant_or_403(current_user),
        action_id=action_id,
    )
    return _to_action_response(action)


@router.post("/actions/lease", response_model=ActionExecutionResponse | None)
@rate_limit("240/minute")
async def lease_action_request(
    request: Request,
    payload: ActionLeaseRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse | None:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.lease_next_action(
        tenant_id=tenant_or_403(current_user),
        worker_id=current_user.id,
        action_type=payload.action_type,
    )
    if action is None:
        return None
    return _to_action_response(action)


@router.post("/actions/requests/{action_id}/complete", response_model=ActionExecutionResponse)
@rate_limit("240/minute")
async def complete_action_request(
    request: Request,
    action_id: UUID,
    payload: ActionCompleteRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.complete_action(
        tenant_id=tenant_or_403(current_user),
        action_id=action_id,
        worker_id=current_user.id,
        result_payload=payload.result_payload,
    )
    return _to_action_response(action)


@router.post("/actions/requests/{action_id}/fail", response_model=ActionExecutionResponse)
@rate_limit("240/minute")
async def fail_action_request(
    request: Request,
    action_id: UUID,
    payload: ActionFailRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.fail_action(
        tenant_id=tenant_or_403(current_user),
        action_id=action_id,
        worker_id=current_user.id,
        error_code=payload.error_code,
        error_message=payload.error_message,
        retryable=payload.retryable,
        result_payload=payload.result_payload,
    )
    return _to_action_response(action)


@router.post("/actions/requests/{action_id}/cancel", response_model=ActionExecutionResponse)
@rate_limit("120/minute")
async def cancel_action_request(
    request: Request,
    action_id: UUID,
    payload: ActionCancelRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> ActionExecutionResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.POLICY_CONFIGURATION,
    )
    service = EnforcementActionOrchestrator(db)
    action = await service.cancel_action(
        tenant_id=tenant_or_403(current_user),
        action_id=action_id,
        actor_id=current_user.id,
        reason=payload.reason,
    )
    return _to_action_response(action)
