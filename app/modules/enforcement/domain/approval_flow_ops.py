from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Mapping, cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementDecision,
    EnforcementDecisionType,
    EnforcementSource,
)
from app.shared.core.auth import CurrentUser


async def create_or_get_approval_request(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    actor_id: UUID,
    decision_id: UUID,
    notes: str | None,
    get_or_create_policy_fn: Callable[[UUID], Awaitable[Any]],
    get_approval_by_decision_fn: Callable[[UUID], Awaitable[EnforcementApprovalRequest | None]],
    resolve_approval_routing_trace_fn: Callable[..., Mapping[str, Any]],
    append_decision_ledger_entry_fn: Callable[..., None],
    utcnow_fn: Callable[[], datetime],
) -> EnforcementApprovalRequest:
    decision = (
        await db.execute(
            select(EnforcementDecision).where(
                EnforcementDecision.id == decision_id,
                EnforcementDecision.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    if decision.decision != EnforcementDecisionType.REQUIRE_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail="Approval request can only be created for REQUIRE_APPROVAL decisions",
        )

    existing = await get_approval_by_decision_fn(decision_id)
    if existing is not None:
        return existing

    policy = await get_or_create_policy_fn(tenant_id)
    ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))
    now = utcnow_fn()
    approval_routing_trace = resolve_approval_routing_trace_fn(
        policy=policy,
        decision=decision,
    )

    approval = EnforcementApprovalRequest(
        tenant_id=tenant_id,
        decision_id=decision_id,
        status=EnforcementApprovalStatus.PENDING,
        requested_by_user_id=actor_id,
        review_notes=(str(notes).strip() if notes else None),
        routing_rule_id=(str(approval_routing_trace.get("rule_id") or "").strip() or None),
        routing_trace=approval_routing_trace,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    db.add(approval)
    await db.flush()
    append_decision_ledger_entry_fn(
        decision_row=decision,
        approval_row=approval,
    )
    await db.commit()
    await db.refresh(approval)
    return approval


async def list_pending_approvals(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    reviewer: CurrentUser | None,
    limit: int,
    get_or_create_policy_fn: Callable[[UUID], Awaitable[Any]],
    enforce_reviewer_authority_fn: Callable[..., Awaitable[Mapping[str, Any]]],
    utcnow_fn: Callable[[], datetime],
) -> list[tuple[EnforcementApprovalRequest, EnforcementDecision]]:
    now = utcnow_fn()
    rows = await db.execute(
        select(EnforcementApprovalRequest, EnforcementDecision)
        .join(
            EnforcementDecision,
            EnforcementDecision.id == EnforcementApprovalRequest.decision_id,
        )
        .where(EnforcementApprovalRequest.tenant_id == tenant_id)
        .where(EnforcementApprovalRequest.status == EnforcementApprovalStatus.PENDING)
        .where(EnforcementApprovalRequest.expires_at >= now)
        .order_by(EnforcementApprovalRequest.created_at.asc())
        .limit(max(1, min(limit, 200)))
    )
    pending = [(row[0], row[1]) for row in rows.all()]
    if reviewer is None:
        return pending

    policy = await get_or_create_policy_fn(tenant_id)
    allowed: list[tuple[EnforcementApprovalRequest, EnforcementDecision]] = []
    for approval, decision in pending:
        try:
            await enforce_reviewer_authority_fn(
                tenant_id=tenant_id,
                policy=policy,
                approval=approval,
                decision=decision,
                reviewer=reviewer,
                enforce_requester_separation=False,
            )
        except HTTPException:
            continue
        allowed.append((approval, decision))
    return allowed


async def approve_request(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    approval_id: UUID,
    reviewer: CurrentUser,
    notes: str | None,
    load_approval_with_decision_fn: Callable[..., Awaitable[tuple[EnforcementApprovalRequest, EnforcementDecision]]],
    assert_pending_fn: Callable[[EnforcementApprovalRequest], None],
    settle_credit_reservations_for_decision_fn: Callable[..., Awaitable[list[dict[str, str]]]],
    get_or_create_policy_fn: Callable[[UUID], Awaitable[Any]],
    enforce_reviewer_authority_fn: Callable[..., Awaitable[Mapping[str, Any]]],
    build_approval_token_fn: Callable[..., str],
    append_decision_ledger_entry_fn: Callable[..., None],
    utcnow_fn: Callable[[], datetime],
    as_utc_fn: Callable[[datetime], datetime],
) -> tuple[EnforcementApprovalRequest, EnforcementDecision, str, datetime]:
    approval, decision = await load_approval_with_decision_fn(
        tenant_id=tenant_id,
        approval_id=approval_id,
    )
    assert_pending_fn(approval)

    now = utcnow_fn()
    approval_expires_at = as_utc_fn(approval.expires_at)
    if approval_expires_at <= now:
        approval.status = EnforcementApprovalStatus.EXPIRED
        approval.updated_at = now
        credit_settlement = await settle_credit_reservations_for_decision_fn(
            tenant_id=tenant_id,
            decision=decision,
            consumed_credit_usd=Decimal("0"),
            now=now,
        )
        decision.reservation_active = False
        decision.reserved_allocation_usd = Decimal("0")
        decision.reserved_credit_usd = Decimal("0")
        decision.response_payload = {
            **(decision.response_payload or {}),
            "approval_expired_at": now.isoformat(),
            "credit_settlement": credit_settlement,
        }
        append_decision_ledger_entry_fn(
            decision_row=decision,
            approval_row=approval,
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="Approval request has expired")

    policy = await get_or_create_policy_fn(tenant_id)
    routing_trace = await enforce_reviewer_authority_fn(
        tenant_id=tenant_id,
        policy=policy,
        approval=approval,
        decision=decision,
        reviewer=reviewer,
        enforce_requester_separation=True,
    )
    ttl_seconds = max(60, min(int(policy.default_ttl_seconds), 86400))
    token_expires_at = now + timedelta(seconds=ttl_seconds)
    approval_token = build_approval_token_fn(
        decision=decision,
        approval=approval,
        expires_at=token_expires_at,
    )

    approval.status = EnforcementApprovalStatus.APPROVED
    approval.reviewed_by_user_id = reviewer.id
    approval.review_notes = (str(notes).strip() if notes else None)
    approval.approved_at = now
    approval.updated_at = now
    approval.approval_token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
    approval.approval_token_expires_at = token_expires_at

    decision.approval_token_issued = True
    decision.token_expires_at = token_expires_at
    decision.response_payload = {
        **(decision.response_payload or {}),
        "approval_id": str(approval.id),
        "approval_routing_rule_id": str(routing_trace.get("rule_id") or ""),
        "approval_routing_trace": routing_trace,
        "approved_by_user_id": str(reviewer.id),
        "approved_at": now.isoformat(),
    }
    append_decision_ledger_entry_fn(
        decision_row=decision,
        approval_row=approval,
    )

    await db.commit()
    await db.refresh(approval)
    await db.refresh(decision)

    return approval, decision, approval_token, token_expires_at


async def deny_request(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    approval_id: UUID,
    reviewer: CurrentUser,
    notes: str | None,
    load_approval_with_decision_fn: Callable[..., Awaitable[tuple[EnforcementApprovalRequest, EnforcementDecision]]],
    assert_pending_fn: Callable[[EnforcementApprovalRequest], None],
    get_or_create_policy_fn: Callable[[UUID], Awaitable[Any]],
    enforce_reviewer_authority_fn: Callable[..., Awaitable[Mapping[str, Any]]],
    settle_credit_reservations_for_decision_fn: Callable[..., Awaitable[list[dict[str, str]]]],
    append_decision_ledger_entry_fn: Callable[..., None],
    utcnow_fn: Callable[[], datetime],
) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
    approval, decision = await load_approval_with_decision_fn(
        tenant_id=tenant_id,
        approval_id=approval_id,
    )
    assert_pending_fn(approval)
    policy = await get_or_create_policy_fn(tenant_id)
    routing_trace = await enforce_reviewer_authority_fn(
        tenant_id=tenant_id,
        policy=policy,
        approval=approval,
        decision=decision,
        reviewer=reviewer,
        enforce_requester_separation=True,
    )

    now = utcnow_fn()
    approval.status = EnforcementApprovalStatus.DENIED
    approval.reviewed_by_user_id = reviewer.id
    approval.review_notes = (str(notes).strip() if notes else None)
    approval.denied_at = now
    approval.updated_at = now

    credit_settlement = await settle_credit_reservations_for_decision_fn(
        tenant_id=tenant_id,
        decision=decision,
        consumed_credit_usd=Decimal("0"),
        now=now,
    )
    decision.reservation_active = False
    decision.reserved_allocation_usd = Decimal("0")
    decision.reserved_credit_usd = Decimal("0")
    decision.response_payload = {
        **(decision.response_payload or {}),
        "approval_id": str(approval.id),
        "approval_routing_rule_id": str(routing_trace.get("rule_id") or ""),
        "approval_routing_trace": routing_trace,
        "denied_by_user_id": str(reviewer.id),
        "denied_at": now.isoformat(),
        "credit_settlement": credit_settlement,
    }
    append_decision_ledger_entry_fn(
        decision_row=decision,
        approval_row=approval,
    )

    await db.commit()
    await db.refresh(approval)
    await db.refresh(decision)

    return approval, decision


async def consume_approval_token(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    approval_token: str,
    actor_id: UUID | None,
    expected_source: EnforcementSource | None,
    expected_project_id: str | None,
    expected_environment: str | None,
    expected_request_fingerprint: str | None,
    expected_resource_reference: str | None,
    decode_approval_token_fn: Callable[[str], Mapping[str, Any]],
    extract_token_context_fn: Callable[[Mapping[str, Any]], Any],
    load_approval_with_decision_fn: Callable[..., Awaitable[tuple[EnforcementApprovalRequest, EnforcementDecision]]],
    utcnow_fn: Callable[[], datetime],
    as_utc_fn: Callable[[datetime], datetime],
    normalize_environment_fn: Callable[[str], str],
    quantize_fn: Callable[[Decimal, str], Decimal],
    to_decimal_fn: Callable[[Any], Decimal],
    approval_token_events_counter: Any,
) -> tuple[EnforcementApprovalRequest, EnforcementDecision]:
    def _token_reject(*, event: str, status_code: int, detail: str) -> None:
        approval_token_events_counter.labels(event=event).inc()
        raise HTTPException(status_code=status_code, detail=detail)

    normalized_token = str(approval_token or "").strip()
    if not normalized_token:
        _token_reject(
            event="token_missing",
            status_code=422,
            detail="approval_token is required",
        )

    token_payload = decode_approval_token_fn(normalized_token)
    token_context = extract_token_context_fn(token_payload)
    if token_context.tenant_id != tenant_id:
        _token_reject(
            event="tenant_mismatch",
            status_code=403,
            detail="Approval token tenant mismatch",
        )

    approval, decision = await load_approval_with_decision_fn(
        tenant_id=tenant_id,
        approval_id=token_context.approval_id,
    )
    if decision.id != token_context.decision_id:
        _token_reject(
            event="decision_binding_mismatch",
            status_code=409,
            detail="Approval token decision binding mismatch",
        )
    if approval.status != EnforcementApprovalStatus.APPROVED:
        _token_reject(
            event="status_not_active",
            status_code=409,
            detail=f"Approval token is not active ({approval.status.value})",
        )

    computed_hash = hashlib.sha256(normalized_token.encode("utf-8")).hexdigest()
    if not approval.approval_token_hash or approval.approval_token_hash != computed_hash:
        _token_reject(
            event="token_hash_mismatch",
            status_code=409,
            detail="Approval token mismatch",
        )

    now = utcnow_fn()
    effective_expiry = as_utc_fn(
        approval.approval_token_expires_at
        or decision.token_expires_at
        or token_context.expires_at
    )
    if effective_expiry <= now:
        _token_reject(
            event="token_expired",
            status_code=409,
            detail="Approval token has expired",
        )

    if token_context.source != decision.source:
        _token_reject(
            event="source_mismatch",
            status_code=409,
            detail="Approval token source mismatch",
        )
    if token_context.project_id != decision.project_id:
        _token_reject(
            event="project_binding_mismatch",
            status_code=409,
            detail="Approval token project binding mismatch",
        )
    if normalize_environment_fn(token_context.environment) != normalize_environment_fn(
        decision.environment
    ):
        _token_reject(
            event="environment_mismatch",
            status_code=409,
            detail="Approval token environment mismatch",
        )
    if token_context.request_fingerprint != decision.request_fingerprint:
        _token_reject(
            event="fingerprint_mismatch",
            status_code=409,
            detail="Approval token fingerprint mismatch",
        )
    if token_context.resource_reference != decision.resource_reference:
        _token_reject(
            event="resource_binding_mismatch",
            status_code=409,
            detail="Approval token resource binding mismatch",
        )
    if quantize_fn(token_context.max_monthly_delta_usd, "0.0001") != quantize_fn(
        to_decimal_fn(decision.estimated_monthly_delta_usd),
        "0.0001",
    ):
        _token_reject(
            event="cost_binding_mismatch",
            status_code=409,
            detail="Approval token cost binding mismatch",
        )
    if quantize_fn(token_context.max_hourly_delta_usd, "0.000001") != quantize_fn(
        to_decimal_fn(decision.estimated_hourly_delta_usd),
        "0.000001",
    ):
        _token_reject(
            event="cost_binding_mismatch",
            status_code=409,
            detail="Approval token cost binding mismatch",
        )

    if expected_source is not None and expected_source != decision.source:
        _token_reject(
            event="expected_source_mismatch",
            status_code=409,
            detail="Expected source mismatch",
        )
    if expected_project_id is not None and str(expected_project_id).strip() != str(
        decision.project_id
    ).strip():
        _token_reject(
            event="expected_project_mismatch",
            status_code=409,
            detail="Expected project mismatch",
        )
    if expected_environment is not None and normalize_environment_fn(
        expected_environment
    ) != normalize_environment_fn(decision.environment):
        _token_reject(
            event="expected_environment_mismatch",
            status_code=409,
            detail="Expected environment mismatch",
        )
    if expected_request_fingerprint is not None and str(
        expected_request_fingerprint
    ).strip() != decision.request_fingerprint:
        _token_reject(
            event="expected_fingerprint_mismatch",
            status_code=409,
            detail="Expected request fingerprint mismatch",
        )
    if expected_resource_reference is not None and str(
        expected_resource_reference
    ).strip() != decision.resource_reference:
        _token_reject(
            event="expected_resource_reference_mismatch",
            status_code=409,
            detail="Expected resource reference mismatch",
        )

    consume_result = cast(
        CursorResult[Any],
        await db.execute(
            update(EnforcementApprovalRequest)
            .where(EnforcementApprovalRequest.id == approval.id)
            .where(EnforcementApprovalRequest.tenant_id == tenant_id)
            .where(EnforcementApprovalRequest.approval_token_consumed_at.is_(None))
            .values(
                approval_token_consumed_at=now,
                updated_at=now,
            ),
        ),
    )
    consumed = int(consume_result.rowcount or 0)
    if consumed != 1:
        await db.rollback()
        _token_reject(
            event="replay_detected",
            status_code=409,
            detail="Approval token replay detected",
        )

    decision.response_payload = {
        **(decision.response_payload or {}),
        "approval_token_consumed_at": now.isoformat(),
        "approval_token_consumed_by_user_id": str(actor_id) if actor_id else None,
    }
    await db.commit()
    approval_token_events_counter.labels(event="consumed").inc()
    await db.refresh(approval)
    await db.refresh(decision)
    return approval, decision
