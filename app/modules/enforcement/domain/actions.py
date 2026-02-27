from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping, cast
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import (
    EnforcementActionExecution,
    EnforcementActionStatus,
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementDecision,
    EnforcementDecisionType,
    EnforcementPolicy,
)
from app.modules.enforcement.domain.policy_document import PolicyDocument

_DEFAULT_ACTION_MAX_ATTEMPTS = 3
_DEFAULT_ACTION_RETRY_BACKOFF_SECONDS = 60
_DEFAULT_ACTION_LEASE_TTL_SECONDS = 300


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_sha256(payload: Mapping[str, Any] | None) -> str:
    serialized = json.dumps(
        dict(payload or {}),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_action_type(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_target_reference(value: str) -> str:
    return str(value or "").strip()


def _normalized_idempotency_key(value: str | None) -> str | None:
    key = str(value or "").strip()
    if not key:
        return None
    return key[:128]


class EnforcementActionOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_policy_execution_controls(
        self,
        *,
        tenant_id: UUID,
    ) -> tuple[int, int, int]:
        policy = (
            await self.db.execute(
                select(EnforcementPolicy).where(EnforcementPolicy.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        if policy is None:
            return (
                _DEFAULT_ACTION_MAX_ATTEMPTS,
                _DEFAULT_ACTION_RETRY_BACKOFF_SECONDS,
                _DEFAULT_ACTION_LEASE_TTL_SECONDS,
            )

        policy_document_raw = (
            policy.policy_document if isinstance(policy.policy_document, Mapping) else {}
        )
        try:
            policy_document = PolicyDocument.model_validate(policy_document_raw)
        except ValidationError:
            return (
                _DEFAULT_ACTION_MAX_ATTEMPTS,
                _DEFAULT_ACTION_RETRY_BACKOFF_SECONDS,
                _DEFAULT_ACTION_LEASE_TTL_SECONDS,
            )
        execution = policy_document.execution
        return (
            max(1, min(int(execution.action_max_attempts), 10)),
            max(1, min(int(execution.action_retry_backoff_seconds), 86400)),
            max(30, min(int(execution.action_lease_ttl_seconds), 3600)),
        )

    async def _resolve_decision_and_approval(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
    ) -> tuple[EnforcementDecision, EnforcementApprovalRequest | None]:
        decision = (
            await self.db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.tenant_id == tenant_id,
                    EnforcementDecision.id == decision_id,
                )
            )
        ).scalar_one_or_none()
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")

        approval = (
            await self.db.execute(
                select(EnforcementApprovalRequest).where(
                    EnforcementApprovalRequest.tenant_id == tenant_id,
                    EnforcementApprovalRequest.decision_id == decision.id,
                )
            )
        ).scalar_one_or_none()
        return decision, approval

    async def _assert_action_request_allowed(
        self,
        *,
        decision: EnforcementDecision,
        approval: EnforcementApprovalRequest | None,
    ) -> UUID | None:
        if decision.decision == EnforcementDecisionType.DENY:
            raise HTTPException(
                status_code=409,
                detail="Cannot enqueue action for denied decision",
            )

        if decision.approval_required:
            if approval is None or approval.status != EnforcementApprovalStatus.APPROVED:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Cannot enqueue action before approval is approved for "
                        "approval-required decision"
                    ),
                )
            return approval.id

        if approval is None or approval.status != EnforcementApprovalStatus.APPROVED:
            return None
        return approval.id

    async def create_action_request(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        decision_id: UUID,
        action_type: str,
        target_reference: str,
        request_payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
        max_attempts: int | None = None,
        retry_backoff_seconds: int | None = None,
        lease_ttl_seconds: int | None = None,
    ) -> EnforcementActionExecution:
        normalized_action_type = _normalize_action_type(action_type)
        if not normalized_action_type:
            raise HTTPException(status_code=422, detail="action_type is required")
        if len(normalized_action_type) > 64:
            raise HTTPException(
                status_code=422,
                detail="action_type must be <= 64 characters",
            )

        normalized_target_reference = _normalize_target_reference(target_reference)
        if not normalized_target_reference:
            raise HTTPException(status_code=422, detail="target_reference is required")
        if len(normalized_target_reference) > 512:
            raise HTTPException(
                status_code=422,
                detail="target_reference must be <= 512 characters",
            )

        decision, approval = await self._resolve_decision_and_approval(
            tenant_id=tenant_id,
            decision_id=decision_id,
        )
        approval_request_id = await self._assert_action_request_allowed(
            decision=decision,
            approval=approval,
        )

        policy_max_attempts, policy_retry_backoff_seconds, policy_lease_ttl_seconds = (
            await self._resolve_policy_execution_controls(tenant_id=tenant_id)
        )
        effective_max_attempts = (
            int(max_attempts) if max_attempts is not None else policy_max_attempts
        )
        effective_retry_backoff_seconds = (
            int(retry_backoff_seconds)
            if retry_backoff_seconds is not None
            else policy_retry_backoff_seconds
        )
        effective_lease_ttl_seconds = (
            int(lease_ttl_seconds)
            if lease_ttl_seconds is not None
            else policy_lease_ttl_seconds
        )
        if effective_max_attempts < 1 or effective_max_attempts > 10:
            raise HTTPException(
                status_code=422,
                detail="max_attempts must be between 1 and 10",
            )
        if (
            effective_retry_backoff_seconds < 1
            or effective_retry_backoff_seconds > 86400
        ):
            raise HTTPException(
                status_code=422,
                detail="retry_backoff_seconds must be between 1 and 86400",
            )
        if effective_lease_ttl_seconds < 30 or effective_lease_ttl_seconds > 3600:
            raise HTTPException(
                status_code=422,
                detail="lease_ttl_seconds must be between 30 and 3600",
            )

        normalized_payload = dict(request_payload or {})
        payload_sha256 = _json_sha256(normalized_payload)
        normalized_idempotency_key = _normalized_idempotency_key(idempotency_key)
        if normalized_idempotency_key is None:
            normalized_idempotency_key = hashlib.sha256(
                (
                    f"{decision.id}:{normalized_action_type}:"
                    f"{normalized_target_reference}:{payload_sha256}"
                ).encode("utf-8")
            ).hexdigest()[:40]

        existing = (
            await self.db.execute(
                select(EnforcementActionExecution).where(
                    EnforcementActionExecution.tenant_id == tenant_id,
                    EnforcementActionExecution.decision_id == decision.id,
                    EnforcementActionExecution.action_type == normalized_action_type,
                    EnforcementActionExecution.idempotency_key
                    == normalized_idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = _utcnow()
        action = EnforcementActionExecution(
            tenant_id=tenant_id,
            decision_id=decision.id,
            approval_request_id=approval_request_id,
            action_type=normalized_action_type,
            target_reference=normalized_target_reference,
            idempotency_key=normalized_idempotency_key,
            request_payload=normalized_payload,
            request_payload_sha256=payload_sha256,
            status=EnforcementActionStatus.QUEUED,
            attempt_count=0,
            max_attempts=effective_max_attempts,
            retry_backoff_seconds=effective_retry_backoff_seconds,
            lease_ttl_seconds=effective_lease_ttl_seconds,
            next_retry_at=now,
            created_by_user_id=actor_id,
        )
        self.db.add(action)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            deduped = (
                await self.db.execute(
                    select(EnforcementActionExecution).where(
                        EnforcementActionExecution.tenant_id == tenant_id,
                        EnforcementActionExecution.decision_id == decision.id,
                        EnforcementActionExecution.action_type == normalized_action_type,
                        EnforcementActionExecution.idempotency_key
                        == normalized_idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if deduped is None:
                raise
            return deduped

        await self.db.refresh(action)
        return action

    async def get_action(
        self,
        *,
        tenant_id: UUID,
        action_id: UUID,
    ) -> EnforcementActionExecution:
        action = (
            await self.db.execute(
                select(EnforcementActionExecution).where(
                    EnforcementActionExecution.tenant_id == tenant_id,
                    EnforcementActionExecution.id == action_id,
                )
            )
        ).scalar_one_or_none()
        if action is None:
            raise HTTPException(status_code=404, detail="Action execution not found")
        return action

    async def list_actions(
        self,
        *,
        tenant_id: UUID,
        status: EnforcementActionStatus | None = None,
        decision_id: UUID | None = None,
        limit: int = 100,
    ) -> list[EnforcementActionExecution]:
        bounded_limit = max(1, min(int(limit), 500))
        stmt = select(EnforcementActionExecution).where(
            EnforcementActionExecution.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(EnforcementActionExecution.status == status)
        if decision_id is not None:
            stmt = stmt.where(EnforcementActionExecution.decision_id == decision_id)
        stmt = stmt.order_by(EnforcementActionExecution.created_at.desc()).limit(
            bounded_limit
        )
        rows = await self.db.execute(stmt)
        return list(rows.scalars().all())

    async def lease_next_action(
        self,
        *,
        tenant_id: UUID,
        worker_id: UUID,
        action_type: str | None = None,
        now: datetime | None = None,
    ) -> EnforcementActionExecution | None:
        as_of = _as_utc(now) if now is not None else _utcnow()
        normalized_action_type = (
            _normalize_action_type(action_type) if action_type is not None else None
        )

        for _ in range(5):
            stmt = (
                select(EnforcementActionExecution)
                .where(
                    EnforcementActionExecution.tenant_id == tenant_id,
                    EnforcementActionExecution.status == EnforcementActionStatus.QUEUED,
                    EnforcementActionExecution.next_retry_at <= as_of,
                    EnforcementActionExecution.attempt_count
                    < EnforcementActionExecution.max_attempts,
                    or_(
                        EnforcementActionExecution.lease_expires_at.is_(None),
                        EnforcementActionExecution.lease_expires_at <= as_of,
                    ),
                )
                .order_by(
                    EnforcementActionExecution.next_retry_at.asc(),
                    EnforcementActionExecution.created_at.asc(),
                )
                .limit(1)
            )
            if normalized_action_type is not None:
                stmt = stmt.where(
                    EnforcementActionExecution.action_type == normalized_action_type
                )

            candidate = (await self.db.execute(stmt)).scalar_one_or_none()
            if candidate is None:
                return None

            lease_expires_at = as_of + timedelta(seconds=int(candidate.lease_ttl_seconds))
            claim_result = cast(
                CursorResult[Any],
                await self.db.execute(
                update(EnforcementActionExecution)
                .where(
                    EnforcementActionExecution.id == candidate.id,
                    EnforcementActionExecution.tenant_id == tenant_id,
                    EnforcementActionExecution.status == EnforcementActionStatus.QUEUED,
                    EnforcementActionExecution.attempt_count == candidate.attempt_count,
                    or_(
                        EnforcementActionExecution.lease_expires_at.is_(None),
                        EnforcementActionExecution.lease_expires_at <= as_of,
                    ),
                )
                .values(
                    status=EnforcementActionStatus.RUNNING,
                    attempt_count=int(candidate.attempt_count) + 1,
                    locked_by_worker_id=worker_id,
                    lease_expires_at=lease_expires_at,
                    started_at=(candidate.started_at or as_of),
                )
            ),
            )
            if int(claim_result.rowcount or 0) <= 0:
                await self.db.rollback()
                continue

            await self.db.commit()
            return await self.get_action(tenant_id=tenant_id, action_id=candidate.id)

        return None

    async def complete_action(
        self,
        *,
        tenant_id: UUID,
        action_id: UUID,
        worker_id: UUID,
        result_payload: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> EnforcementActionExecution:
        action = await self.get_action(tenant_id=tenant_id, action_id=action_id)
        if action.status != EnforcementActionStatus.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="Only running actions can be completed",
            )
        if action.locked_by_worker_id is not None and action.locked_by_worker_id != worker_id:
            raise HTTPException(
                status_code=409,
                detail="Action lease is owned by another worker",
            )

        completed_at = _as_utc(now) if now is not None else _utcnow()
        normalized_result_payload = dict(result_payload or {})
        action.status = EnforcementActionStatus.SUCCEEDED
        action.result_payload = normalized_result_payload
        action.result_payload_sha256 = _json_sha256(normalized_result_payload)
        action.last_error_code = None
        action.last_error_message = None
        action.locked_by_worker_id = None
        action.lease_expires_at = None
        action.completed_at = completed_at
        action.next_retry_at = completed_at
        await self.db.commit()
        await self.db.refresh(action)
        return action

    async def fail_action(
        self,
        *,
        tenant_id: UUID,
        action_id: UUID,
        worker_id: UUID,
        error_code: str,
        error_message: str,
        retryable: bool,
        result_payload: Mapping[str, Any] | None = None,
        now: datetime | None = None,
    ) -> EnforcementActionExecution:
        action = await self.get_action(tenant_id=tenant_id, action_id=action_id)
        if action.status != EnforcementActionStatus.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="Only running actions can be failed",
            )
        if action.locked_by_worker_id is not None and action.locked_by_worker_id != worker_id:
            raise HTTPException(
                status_code=409,
                detail="Action lease is owned by another worker",
            )

        normalized_error_code = str(error_code or "").strip().lower()
        if not normalized_error_code:
            raise HTTPException(status_code=422, detail="error_code is required")
        if len(normalized_error_code) > 64:
            raise HTTPException(
                status_code=422,
                detail="error_code must be <= 64 characters",
            )
        normalized_error_message = str(error_message or "").strip()
        if not normalized_error_message:
            raise HTTPException(status_code=422, detail="error_message is required")
        if len(normalized_error_message) > 1000:
            raise HTTPException(
                status_code=422,
                detail="error_message must be <= 1000 characters",
            )

        failed_at = _as_utc(now) if now is not None else _utcnow()
        normalized_result_payload = dict(result_payload or {})
        if not normalized_result_payload:
            normalized_result_payload = {
                "error_code": normalized_error_code,
                "error_message": normalized_error_message,
                "retryable": bool(retryable),
            }

        should_retry = bool(retryable) and int(action.attempt_count) < int(action.max_attempts)
        action.last_error_code = normalized_error_code
        action.last_error_message = normalized_error_message
        action.result_payload = normalized_result_payload
        action.result_payload_sha256 = _json_sha256(normalized_result_payload)
        action.locked_by_worker_id = None
        action.lease_expires_at = None

        if should_retry:
            action.status = EnforcementActionStatus.QUEUED
            action.next_retry_at = failed_at + timedelta(
                seconds=int(action.retry_backoff_seconds)
            )
            action.completed_at = None
        else:
            action.status = EnforcementActionStatus.FAILED
            action.next_retry_at = failed_at
            action.completed_at = failed_at

        await self.db.commit()
        await self.db.refresh(action)
        return action

    async def cancel_action(
        self,
        *,
        tenant_id: UUID,
        action_id: UUID,
        actor_id: UUID,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> EnforcementActionExecution:
        action = await self.get_action(tenant_id=tenant_id, action_id=action_id)
        if action.status in {
            EnforcementActionStatus.SUCCEEDED,
            EnforcementActionStatus.FAILED,
            EnforcementActionStatus.CANCELLED,
        }:
            raise HTTPException(
                status_code=409,
                detail="Terminal action cannot be cancelled",
            )

        cancelled_at = _as_utc(now) if now is not None else _utcnow()
        action.status = EnforcementActionStatus.CANCELLED
        action.locked_by_worker_id = None
        action.lease_expires_at = None
        action.completed_at = cancelled_at
        action.next_retry_at = cancelled_at
        if reason is not None:
            normalized_reason = str(reason).strip()
            action.last_error_code = "cancelled"
            action.last_error_message = normalized_reason[:1000] or "cancelled"
            action.result_payload = {
                "cancelled_by": str(actor_id),
                "reason": action.last_error_message,
            }
            action.result_payload_sha256 = _json_sha256(action.result_payload)

        await self.db.commit()
        await self.db.refresh(action)
        return action
