from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.enforcement import (
    EnforcementActionStatus,
    EnforcementApprovalRequest,
    EnforcementApprovalStatus,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)
from app.models.tenant import Tenant, UserRole
from app.modules.enforcement.domain.actions import (
    EnforcementActionOrchestrator,
    _as_utc,
    _normalized_idempotency_key,
)
from app.modules.enforcement.domain.service import EnforcementService, GateInput
from app.shared.core.auth import CurrentUser


async def _seed_tenant(db) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="Enforcement Actions Tenant",
        plan="enterprise",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _seed_pending_approval_decision(
    *,
    db,
    tenant_id,
    actor_id,
    idempotency_key: str,
):
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )
    return await service.evaluate_gate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.pending",
            estimated_monthly_delta_usd=Decimal("40"),
            estimated_hourly_delta_usd=Decimal("0.05"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key=idempotency_key,
        ),
    )


async def _seed_approved_decision(
    *,
    db,
    tenant_id,
    actor_id,
    idempotency_key: str,
):
    gate = await _seed_pending_approval_decision(
        db=db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    assert gate.approval is not None
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@valdrix.local",
        tenant_id=tenant_id,
        role=UserRole.OWNER,
    )
    approval, decision, _, _ = await service.approve_request(
        tenant_id=tenant_id,
        approval_id=gate.approval.id,
        reviewer=reviewer,
        notes="approve for action orchestration tests",
    )
    return approval, decision


async def _seed_denied_decision(
    *,
    db,
    tenant_id,
    actor_id,
    idempotency_key: str,
):
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.HARD,
        k8s_admission_mode=EnforcementMode.HARD,
        k8s_admission_mode_nonprod=EnforcementMode.HARD,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    result = await service.evaluate_gate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.denied",
            estimated_monthly_delta_usd=Decimal("50"),
            estimated_hourly_delta_usd=Decimal("0.07"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key=idempotency_key,
        ),
    )
    assert result.decision.decision == EnforcementDecisionType.DENY
    return result.decision


async def _seed_allow_decision(
    *,
    db,
    tenant_id,
    actor_id,
    idempotency_key: str,
):
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("1000"),
        hard_deny_above_monthly_usd=Decimal("5000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )
    result = await service.evaluate_gate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.allow",
            estimated_monthly_delta_usd=Decimal("40"),
            estimated_hourly_delta_usd=Decimal("0.05"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key=idempotency_key,
        ),
    )
    assert result.decision.decision == EnforcementDecisionType.ALLOW
    assert result.decision.approval_required is False
    return result.decision


@pytest.mark.asyncio
async def test_create_action_request_is_idempotent_and_traceable(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    approval, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-idempotent-decision-1",
    )

    orchestrator = EnforcementActionOrchestrator(db)
    first = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform", "workspace": "prod"},
        idempotency_key="action-idempotency-001",
    )
    second = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform", "workspace": "prod"},
        idempotency_key="action-idempotency-001",
    )

    assert first.id == second.id
    assert first.approval_request_id == approval.id
    assert first.status == EnforcementActionStatus.QUEUED
    assert first.attempt_count == 0
    assert len(first.request_payload_sha256) == 64


@pytest.mark.asyncio
async def test_create_action_request_for_allow_decision_without_approval_row(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    decision = await _seed_allow_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-allow-no-approval-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)

    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-allow-no-approval-1",
    )

    assert action.approval_request_id is None


@pytest.mark.asyncio
async def test_create_action_request_for_allow_decision_uses_existing_approved_approval(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    decision = await _seed_allow_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-allow-with-approved-approval-1",
    )
    approved = EnforcementApprovalRequest(
        tenant_id=tenant.id,
        decision_id=decision.id,
        status=EnforcementApprovalStatus.APPROVED,
        requested_by_user_id=actor_id,
        reviewed_by_user_id=uuid4(),
        expires_at=datetime(2026, 2, 26, 0, 0, tzinfo=timezone.utc),
        approved_at=datetime(2026, 2, 25, 0, 0, tzinfo=timezone.utc),
    )
    db.add(approved)
    await db.commit()
    await db.refresh(approved)

    orchestrator = EnforcementActionOrchestrator(db)
    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-allow-with-approved-approval-1",
    )

    assert action.approval_request_id == approved.id


@pytest.mark.asyncio
async def test_create_action_request_rejects_denied_decision(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    denied = await _seed_denied_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-denied-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)

    with pytest.raises(HTTPException) as exc:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=denied.id,
            action_type="terraform.apply.execute",
            target_reference=denied.resource_reference,
            request_payload={"provider": "terraform"},
            idempotency_key="action-denied-001",
        )

    assert exc.value.status_code == 409
    assert "denied decision" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_create_action_request_rejects_unapproved_decision(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _seed_pending_approval_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-pending-decision-1",
    )
    assert gate.decision.approval_required is True
    assert gate.approval is not None
    orchestrator = EnforcementActionOrchestrator(db)

    with pytest.raises(HTTPException) as exc:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=gate.decision.id,
            action_type="terraform.apply.execute",
            target_reference=gate.decision.resource_reference,
            request_payload={"provider": "terraform"},
            idempotency_key="action-pending-001",
        )

    assert exc.value.status_code == 409
    assert "before approval is approved" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_create_action_request_validation_and_lookup_errors(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-validation-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)

    with pytest.raises(HTTPException) as missing_decision:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=uuid4(),
            action_type="terraform.apply.execute",
            target_reference="module.app.aws_instance.missing",
            idempotency_key="action-missing-decision",
        )
    assert missing_decision.value.status_code == 404

    with pytest.raises(HTTPException) as exc_action_required:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="",
            target_reference=decision.resource_reference,
            idempotency_key="action-validation-missing-type",
        )
    assert exc_action_required.value.status_code == 422

    with pytest.raises(HTTPException) as exc_action_too_long:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="a" * 65,
            target_reference=decision.resource_reference,
            idempotency_key="action-validation-type-too-long",
        )
    assert exc_action_too_long.value.status_code == 422

    with pytest.raises(HTTPException) as exc_target_required:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference="",
            idempotency_key="action-validation-target-required",
        )
    assert exc_target_required.value.status_code == 422

    with pytest.raises(HTTPException) as exc_target_too_long:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference="x" * 513,
            idempotency_key="action-validation-target-too-long",
        )
    assert exc_target_too_long.value.status_code == 422

    with pytest.raises(HTTPException) as exc_max_attempts:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference=decision.resource_reference,
            idempotency_key="action-validation-max-attempts",
            max_attempts=0,
        )
    assert exc_max_attempts.value.status_code == 422

    with pytest.raises(HTTPException) as exc_retry:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference=decision.resource_reference,
            idempotency_key="action-validation-retry",
            retry_backoff_seconds=0,
        )
    assert exc_retry.value.status_code == 422

    with pytest.raises(HTTPException) as exc_lease_ttl:
        await orchestrator.create_action_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference=decision.resource_reference,
            idempotency_key="action-validation-lease",
            lease_ttl_seconds=29,
        )
    assert exc_lease_ttl.value.status_code == 422


@pytest.mark.asyncio
async def test_action_retry_is_policy_governed_and_terminal_after_max_attempts(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-retry-policy-decision-1",
    )
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
        policy_document={
            "schema_version": "valdrix.enforcement.policy.v1",
            "mode_matrix": {
                "terraform_default": "soft",
                "terraform_prod": "soft",
                "terraform_nonprod": "soft",
                "k8s_admission_default": "soft",
                "k8s_admission_prod": "soft",
                "k8s_admission_nonprod": "soft",
            },
            "approval": {
                "require_approval_prod": False,
                "require_approval_nonprod": False,
                "enforce_prod_requester_reviewer_separation": True,
                "enforce_nonprod_requester_reviewer_separation": False,
                "routing_rules": [],
            },
            "entitlements": {
                "plan_monthly_ceiling_usd": None,
                "enterprise_monthly_ceiling_usd": None,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "1000",
            },
            "execution": {
                "default_ttl_seconds": 900,
                "action_max_attempts": 2,
                "action_retry_backoff_seconds": 45,
                "action_lease_ttl_seconds": 120,
            },
        },
    )
    orchestrator = EnforcementActionOrchestrator(db)
    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-retry-policy-001",
    )
    assert action.max_attempts == 2
    assert action.retry_backoff_seconds == 45
    assert action.lease_ttl_seconds == 120

    base_time = action.next_retry_at
    if base_time is None:
        base_time = datetime(2026, 2, 25, 10, 0, 0, tzinfo=timezone.utc)
    elif base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    else:
        base_time = base_time.astimezone(timezone.utc)

    first_lease = await orchestrator.lease_next_action(
        tenant_id=tenant.id,
        worker_id=uuid4(),
        now=base_time,
    )
    assert first_lease is not None
    assert first_lease.status == EnforcementActionStatus.RUNNING
    assert first_lease.attempt_count == 1

    first_fail = await orchestrator.fail_action(
        tenant_id=tenant.id,
        action_id=first_lease.id,
        worker_id=first_lease.locked_by_worker_id or uuid4(),
        error_code="provider_timeout",
        error_message="provider timeout",
        retryable=True,
        result_payload={"provider_error": "timeout"},
        now=base_time,
    )
    assert first_fail.status == EnforcementActionStatus.QUEUED
    expected_retry_at = base_time + timedelta(seconds=45)
    actual_retry_at = first_fail.next_retry_at
    if actual_retry_at.tzinfo is None:
        actual_retry_at = actual_retry_at.replace(tzinfo=timezone.utc)
    else:
        actual_retry_at = actual_retry_at.astimezone(timezone.utc)
    assert actual_retry_at == expected_retry_at
    assert first_fail.attempt_count == 1

    second_lease = await orchestrator.lease_next_action(
        tenant_id=tenant.id,
        worker_id=uuid4(),
        now=base_time + timedelta(seconds=46),
    )
    assert second_lease is not None
    assert second_lease.status == EnforcementActionStatus.RUNNING
    assert second_lease.attempt_count == 2

    terminal_fail = await orchestrator.fail_action(
        tenant_id=tenant.id,
        action_id=second_lease.id,
        worker_id=second_lease.locked_by_worker_id or uuid4(),
        error_code="provider_timeout",
        error_message="second timeout",
        retryable=True,
        now=base_time + timedelta(seconds=46),
    )
    assert terminal_fail.status == EnforcementActionStatus.FAILED
    assert terminal_fail.completed_at is not None
    assert terminal_fail.attempt_count == 2


@pytest.mark.asyncio
async def test_complete_action_enforces_worker_lease(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-worker-lock-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)
    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-worker-lock-001",
    )

    worker_id = uuid4()
    leased = await orchestrator.lease_next_action(
        tenant_id=tenant.id,
        worker_id=worker_id,
    )
    assert leased is not None
    assert leased.id == action.id

    with pytest.raises(HTTPException) as exc:
        await orchestrator.complete_action(
            tenant_id=tenant.id,
            action_id=leased.id,
            worker_id=uuid4(),
            result_payload={"status": "ok"},
        )
    assert exc.value.status_code == 409
    assert "another worker" in str(exc.value.detail).lower()

    completed = await orchestrator.complete_action(
        tenant_id=tenant.id,
        action_id=leased.id,
        worker_id=worker_id,
        result_payload={"status": "ok"},
    )
    assert completed.status == EnforcementActionStatus.SUCCEEDED
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_complete_action_requires_running_status(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-complete-status-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)
    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-complete-status-1",
    )

    with pytest.raises(HTTPException) as exc:
        await orchestrator.complete_action(
            tenant_id=tenant.id,
            action_id=action.id,
            worker_id=uuid4(),
            result_payload={"status": "ok"},
        )

    assert exc.value.status_code == 409
    assert "only running actions" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_fail_action_validation_and_terminal_paths(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-fail-branch-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)
    queued = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-fail-branch-queued-1",
    )

    with pytest.raises(HTTPException) as not_running:
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=queued.id,
            worker_id=uuid4(),
            error_code="provider_timeout",
            error_message="timeout",
            retryable=True,
        )
    assert not_running.value.status_code == 409

    running = await orchestrator.lease_next_action(
        tenant_id=tenant.id,
        worker_id=uuid4(),
    )
    assert running is not None

    with pytest.raises(HTTPException) as wrong_worker:
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=running.id,
            worker_id=uuid4(),
            error_code="provider_timeout",
            error_message="timeout",
            retryable=True,
        )
    assert wrong_worker.value.status_code == 409

    with pytest.raises(HTTPException):
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=running.id,
            worker_id=running.locked_by_worker_id or uuid4(),
            error_code="",
            error_message="timeout",
            retryable=True,
        )

    with pytest.raises(HTTPException):
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=running.id,
            worker_id=running.locked_by_worker_id or uuid4(),
            error_code="x" * 65,
            error_message="timeout",
            retryable=True,
        )

    with pytest.raises(HTTPException):
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=running.id,
            worker_id=running.locked_by_worker_id or uuid4(),
            error_code="provider_timeout",
            error_message="",
            retryable=True,
        )

    with pytest.raises(HTTPException):
        await orchestrator.fail_action(
            tenant_id=tenant.id,
            action_id=running.id,
            worker_id=running.locked_by_worker_id or uuid4(),
            error_code="provider_timeout",
            error_message="x" * 1001,
            retryable=True,
        )

    failed = await orchestrator.fail_action(
        tenant_id=tenant.id,
        action_id=running.id,
        worker_id=running.locked_by_worker_id or uuid4(),
        error_code="provider_timeout",
        error_message="terminal timeout",
        retryable=False,
    )
    assert failed.status == EnforcementActionStatus.FAILED
    assert failed.result_payload is not None
    assert failed.result_payload["error_code"] == "provider_timeout"
    assert failed.result_payload["retryable"] is False


@pytest.mark.asyncio
async def test_cancel_action_terminal_guard_and_reason_paths(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    _, decision = await _seed_approved_decision(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="actions-cancel-branch-decision-1",
    )
    orchestrator = EnforcementActionOrchestrator(db)
    action = await orchestrator.create_action_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference=decision.resource_reference,
        request_payload={"provider": "terraform"},
        idempotency_key="action-cancel-branch-1",
    )

    cancelled = await orchestrator.cancel_action(
        tenant_id=tenant.id,
        action_id=action.id,
        actor_id=actor_id,
    )
    assert cancelled.status == EnforcementActionStatus.CANCELLED
    assert cancelled.result_payload is None

    with pytest.raises(HTTPException) as terminal:
        await orchestrator.cancel_action(
            tenant_id=tenant.id,
            action_id=cancelled.id,
            actor_id=actor_id,
            reason="already terminal",
        )
    assert terminal.value.status_code == 409


def test_action_orchestrator_internal_normalizers() -> None:
    naive = datetime(2026, 2, 25, 12, 0, 0)
    normalized_naive = _as_utc(naive)
    assert normalized_naive.tzinfo is not None
    assert normalized_naive.utcoffset() == timedelta(0)

    assert _normalized_idempotency_key(None) is None
    assert _normalized_idempotency_key("   ") is None
    assert _normalized_idempotency_key("  abc123  ") == "abc123"
    assert len(_normalized_idempotency_key("x" * 200) or "") == 128


class _ScalarResult:
    def __init__(self, value) -> None:  # type: ignore[no-untyped-def]
        self._value = value

    def scalar_one_or_none(self):  # type: ignore[no-untyped-def]
        return self._value


class _ScalarsResult:
    def __init__(self, values) -> None:  # type: ignore[no-untyped-def]
        self._values = list(values)

    def all(self):  # type: ignore[no-untyped-def]
        return list(self._values)


class _RowsResult:
    def __init__(self, values) -> None:  # type: ignore[no-untyped-def]
        self._values = list(values)

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._values)


class _RowCountResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _QueueDB:
    def __init__(self, execute_results: list[object]) -> None:
        self._execute_results = list(execute_results)
        self.rollback = AsyncMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()
        self.added: list[object] = []

    async def execute(self, *_args, **_kwargs) -> object:
        if not self._execute_results:
            raise AssertionError("No queued execute result available")
        return self._execute_results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)


@pytest.mark.asyncio
async def test_action_orchestrator_policy_controls_default_and_invalid_paths() -> None:
    missing_policy_db = _QueueDB([_ScalarResult(None)])
    orchestrator = EnforcementActionOrchestrator(missing_policy_db)  # type: ignore[arg-type]
    assert await orchestrator._resolve_policy_execution_controls(tenant_id=uuid4()) == (
        3,
        60,
        300,
    )

    invalid_policy = SimpleNamespace(policy_document={"invalid": "value"})
    invalid_policy_db = _QueueDB([_ScalarResult(invalid_policy)])
    invalid_orchestrator = EnforcementActionOrchestrator(invalid_policy_db)  # type: ignore[arg-type]
    assert await invalid_orchestrator._resolve_policy_execution_controls(tenant_id=uuid4()) == (
        3,
        60,
        300,
    )


@pytest.mark.asyncio
async def test_action_orchestrator_create_auto_idempotency_and_integrity_dedup_paths() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    decision = SimpleNamespace(
        id=uuid4(),
        decision=EnforcementDecisionType.ALLOW,
        approval_required=False,
    )

    # Auto-generated idempotency path (no key provided).
    auto_db = _QueueDB([_ScalarResult(None)])
    auto_orchestrator = EnforcementActionOrchestrator(auto_db)  # type: ignore[arg-type]
    auto_orchestrator._resolve_decision_and_approval = AsyncMock(return_value=(decision, None))
    auto_orchestrator._assert_action_request_allowed = AsyncMock(return_value=None)
    auto_orchestrator._resolve_policy_execution_controls = AsyncMock(return_value=(3, 60, 300))

    auto_action = await auto_orchestrator.create_action_request(
        tenant_id=tenant_id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference="module.app.aws_instance.auto-idem",
        request_payload={"k": "v"},
        idempotency_key=None,
    )
    assert len(auto_action.idempotency_key) == 40

    # IntegrityError dedupe fallback path.
    deduped = SimpleNamespace(id=uuid4())
    dedupe_db = _QueueDB([_ScalarResult(None), _ScalarResult(deduped)])
    dedupe_db.commit = AsyncMock(
        side_effect=IntegrityError("insert", {"x": 1}, RuntimeError("duplicate"))
    )
    dedupe_orchestrator = EnforcementActionOrchestrator(dedupe_db)  # type: ignore[arg-type]
    dedupe_orchestrator._resolve_decision_and_approval = AsyncMock(return_value=(decision, None))
    dedupe_orchestrator._assert_action_request_allowed = AsyncMock(return_value=None)
    dedupe_orchestrator._resolve_policy_execution_controls = AsyncMock(return_value=(3, 60, 300))

    deduped_action = await dedupe_orchestrator.create_action_request(
        tenant_id=tenant_id,
        actor_id=actor_id,
        decision_id=decision.id,
        action_type="terraform.apply.execute",
        target_reference="module.app.aws_instance.dedupe",
        request_payload={"k": "v"},
        idempotency_key="dedupe-key",
    )
    assert deduped_action is deduped
    dedupe_db.rollback.assert_awaited()

    # IntegrityError fallback with no deduped row should re-raise.
    no_dedupe_db = _QueueDB([_ScalarResult(None), _ScalarResult(None)])
    duplicate_error = IntegrityError("insert", {"x": 1}, RuntimeError("duplicate"))
    no_dedupe_db.commit = AsyncMock(side_effect=duplicate_error)
    no_dedupe_orchestrator = EnforcementActionOrchestrator(no_dedupe_db)  # type: ignore[arg-type]
    no_dedupe_orchestrator._resolve_decision_and_approval = AsyncMock(
        return_value=(decision, None)
    )
    no_dedupe_orchestrator._assert_action_request_allowed = AsyncMock(return_value=None)
    no_dedupe_orchestrator._resolve_policy_execution_controls = AsyncMock(
        return_value=(3, 60, 300)
    )

    with pytest.raises(IntegrityError):
        await no_dedupe_orchestrator.create_action_request(
            tenant_id=tenant_id,
            actor_id=actor_id,
            decision_id=decision.id,
            action_type="terraform.apply.execute",
            target_reference="module.app.aws_instance.dedupe-miss",
            request_payload={"k": "v"},
            idempotency_key="dedupe-key-miss",
        )
    no_dedupe_db.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_action_orchestrator_get_list_lease_and_cancel_missing_branches() -> None:
    tenant_id = uuid4()
    decision_id = uuid4()
    action_id = uuid4()

    # get_action not found branch.
    not_found_db = _QueueDB([_ScalarResult(None)])
    not_found_orchestrator = EnforcementActionOrchestrator(not_found_db)  # type: ignore[arg-type]
    with pytest.raises(HTTPException, match="not found"):
        await not_found_orchestrator.get_action(tenant_id=tenant_id, action_id=action_id)

    # list_actions status/decision filters + return conversion path.
    listed_row = SimpleNamespace(id=action_id)
    list_db = _QueueDB([_RowsResult([listed_row])])
    list_orchestrator = EnforcementActionOrchestrator(list_db)  # type: ignore[arg-type]
    listed = await list_orchestrator.list_actions(
        tenant_id=tenant_id,
        status=EnforcementActionStatus.QUEUED,
        decision_id=decision_id,
        limit=10,
    )
    assert listed == [listed_row]

    # status=None branch: list should still return scalars without status filter.
    no_status_row = SimpleNamespace(id=uuid4())
    no_status_db = _QueueDB([_RowsResult([no_status_row])])
    no_status_orchestrator = EnforcementActionOrchestrator(no_status_db)  # type: ignore[arg-type]
    no_status_listed = await no_status_orchestrator.list_actions(
        tenant_id=tenant_id,
        status=None,
        decision_id=None,
        limit=10,
    )
    assert no_status_listed == [no_status_row]

    # lease_next_action early empty-candidate path.
    empty_candidate_db = _QueueDB([_ScalarResult(None)])
    empty_candidate_orchestrator = EnforcementActionOrchestrator(
        empty_candidate_db
    )  # type: ignore[arg-type]
    assert (
        await empty_candidate_orchestrator.lease_next_action(
            tenant_id=tenant_id,
            worker_id=uuid4(),
            action_type="terraform.apply.execute",
            now=datetime.now(timezone.utc),
        )
        is None
    )

    # lease_next_action contention path: candidate found but update rowcount=0 repeatedly.
    candidate = SimpleNamespace(
        id=uuid4(),
        lease_ttl_seconds=300,
        attempt_count=0,
        started_at=None,
    )
    execute_results: list[object] = []
    for _ in range(5):
        execute_results.append(_ScalarResult(candidate))
        execute_results.append(_RowCountResult(0))
    contention_db = _QueueDB(execute_results)
    contention_orchestrator = EnforcementActionOrchestrator(contention_db)  # type: ignore[arg-type]
    leased = await contention_orchestrator.lease_next_action(
        tenant_id=tenant_id,
        worker_id=uuid4(),
        action_type="terraform.apply.execute",
        now=datetime.now(timezone.utc),
    )
    assert leased is None
    assert contention_db.rollback.await_count == 5

    # cancel_action reason branch.
    cancel_db = _QueueDB([])
    cancel_orchestrator = EnforcementActionOrchestrator(cancel_db)  # type: ignore[arg-type]
    cancellable = SimpleNamespace(
        status=EnforcementActionStatus.QUEUED,
        locked_by_worker_id=uuid4(),
        lease_expires_at=datetime.now(timezone.utc),
        completed_at=None,
        next_retry_at=datetime.now(timezone.utc),
        result_payload=None,
        result_payload_sha256=None,
        last_error_code=None,
        last_error_message=None,
    )
    cancel_orchestrator.get_action = AsyncMock(return_value=cancellable)
    cancelled = await cancel_orchestrator.cancel_action(
        tenant_id=tenant_id,
        action_id=uuid4(),
        actor_id=uuid4(),
        reason="  operator cancelled request  ",
    )
    assert cancelled.last_error_code == "cancelled"
    assert cancelled.result_payload is not None
    assert "operator cancelled request" in str(cancelled.result_payload["reason"])
