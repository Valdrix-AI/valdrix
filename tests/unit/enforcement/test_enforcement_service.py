from __future__ import annotations

import asyncio
import base64
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.enforcement.domain.service as enforcement_service_module
from app.models.enforcement import (
    EnforcementApprovalStatus,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)
from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import Tenant, User, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.enforcement.domain.service import EnforcementService, GateInput
from app.shared.core.auth import CurrentUser
from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
)


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._last_labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeCounter":
        self._last_labels = dict(labels)
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append((dict(self._last_labels), float(amount)))


async def _seed_tenant(db) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="Enforcement Test Tenant",
        plan="enterprise",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def _issue_approved_token(
    *,
    db,
    tenant_id,
    actor_id,
    project_id: str = "default",
    environment: str = "prod",
    monthly_delta: Decimal = Decimal("120"),
    idempotency_key: str = "token-issue-1",
) -> tuple[str, object, object]:
    service = EnforcementService(db)
    await service.upsert_budget(
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("2000"),
        active=True,
    )

    gate_result = await service.evaluate_gate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id=project_id,
            environment=environment,
            action="terraform.apply",
            resource_reference="module.rds.aws_db_instance.main",
            estimated_monthly_delta_usd=monthly_delta,
            estimated_hourly_delta_usd=Decimal("0.160"),
            metadata={"resource_type": "aws_db_instance"},
            idempotency_key=idempotency_key,
        ),
    )
    assert gate_result.approval is not None

    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant_id,
        role=UserRole.OWNER,
    )
    approval, decision, token, _ = await service.approve_request(
        tenant_id=tenant_id,
        approval_id=gate_result.approval.id,
        reviewer=reviewer,
        notes="approved for token tests",
    )
    assert isinstance(token, str) and token
    return token, approval, decision


async def _issue_pending_approval(
    *,
    db,
    tenant_id,
    actor_id,
    environment: str,
    require_approval_for_prod: bool,
    require_approval_for_nonprod: bool,
    idempotency_key: str,
):
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=require_approval_for_prod,
        require_approval_for_nonprod=require_approval_for_nonprod,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant_id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )
    gate = await service.evaluate_gate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment=environment,
            action="terraform.apply",
            resource_reference="module.app.aws_instance.web",
            estimated_monthly_delta_usd=Decimal("75"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key=idempotency_key,
        ),
    )
    assert gate.approval is not None
    assert gate.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    return gate


async def _seed_member_scim_permission(
    *,
    db,
    tenant_id,
    member_id,
    permissions: list[str],
    scim_enabled: bool,
    group_name: str = "finops-approvers",
) -> None:
    member = (
        await db.execute(select(User).where(User.id == member_id))
    ).scalar_one_or_none()
    if member is None:
        member = User(
            id=member_id,
            tenant_id=tenant_id,
            email=f"{member_id.hex[:12]}@example.com",
            role=UserRole.MEMBER.value,
            persona="engineering",
            is_active=True,
        )
        db.add(member)
        await db.flush()

    settings = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    if settings is None:
        settings = TenantIdentitySettings(tenant_id=tenant_id)
        db.add(settings)
        await db.flush()

    settings.scim_enabled = bool(scim_enabled)
    settings.scim_group_mappings = [
        {
            "group": group_name,
            "permissions": permissions,
        }
    ]

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == tenant_id,
                ScimGroup.display_name_norm == group_name.strip().lower(),
            )
        )
    ).scalar_one_or_none()
    if group is None:
        group = ScimGroup(
            tenant_id=tenant_id,
            display_name=group_name,
            display_name_norm=group_name.strip().lower(),
            external_id=group_name,
            external_id_norm=group_name.strip().lower(),
        )
        db.add(group)
        await db.flush()

    membership = (
        await db.execute(
            select(ScimGroupMember).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.group_id == group.id,
                ScimGroupMember.user_id == member_id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        db.add(
            ScimGroupMember(
                tenant_id=tenant_id,
                group_id=group.id,
                user_id=member_id,
            )
        )

    await db.commit()


@pytest.mark.asyncio
async def test_evaluate_gate_idempotency_returns_existing_decision(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    payload = GateInput(
        project_id="proj-a",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.ec2.aws_instance.web",
        estimated_monthly_delta_usd=Decimal("12.5"),
        estimated_hourly_delta_usd=Decimal("0.018"),
        metadata={"resource_type": "aws_instance"},
        idempotency_key="idem-key-123",
    )

    first = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )
    second = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )

    assert first.decision.id == second.decision.id
    assert first.decision.decision == EnforcementDecisionType.ALLOW
    assert "no_budget_configured" in (first.decision.reason_codes or [])

    count = (
        await db.execute(
            select(func.count())
            .select_from(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_evaluate_gate_prod_requires_approval_and_creates_pending_request(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("5000"),
        active=True,
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.eks.aws_eks_cluster.main",
            estimated_monthly_delta_usd=Decimal("250"),
            estimated_hourly_delta_usd=Decimal("0.34"),
            metadata={"resource_type": "aws_eks_cluster"},
            idempotency_key="prod-approval-1",
        ),
    )

    assert result.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert result.decision.approval_required is True
    assert result.approval is not None
    assert result.approval.status == EnforcementApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_budget_waterfall_allocates_credit_headroom(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="pilot safety credit",
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="admission.validate",
            resource_reference="deployments/apps/web",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.04"),
            metadata={"namespace": "apps"},
            idempotency_key="credits-waterfall-1",
        ),
    )

    assert result.decision.decision == EnforcementDecisionType.ALLOW_WITH_CREDITS
    assert result.decision.reserved_allocation_usd == Decimal("10.0000")
    assert result.decision.reserved_credit_usd == Decimal("20.0000")
    assert "credit_waterfall_used" in (result.decision.reason_codes or [])


@pytest.mark.asyncio
async def test_approve_request_issues_token_and_marks_decision(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("500"),
        active=True,
    )

    gate_result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.rds.aws_db_instance.main",
            estimated_monthly_delta_usd=Decimal("120"),
            estimated_hourly_delta_usd=Decimal("0.16"),
            metadata={"resource_type": "aws_db_instance"},
            idempotency_key="approve-token-1",
        ),
    )
    assert gate_result.approval is not None

    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )

    approval, decision, token, expires_at = await service.approve_request(
        tenant_id=tenant.id,
        approval_id=gate_result.approval.id,
        reviewer=reviewer,
        notes="approved for launch",
    )

    assert approval.status == EnforcementApprovalStatus.APPROVED
    assert isinstance(token, str) and token
    assert decision.approval_token_issued is True
    assert decision.token_expires_at is not None
    decision_expiry = decision.token_expires_at
    if decision_expiry.tzinfo is None:
        decision_expiry = decision_expiry.replace(tzinfo=timezone.utc)
    assert decision_expiry == expires_at


@pytest.mark.asyncio
async def test_deny_request_releases_existing_reservation(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=True,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )

    gate_result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.ec2.aws_instance.worker",
            estimated_monthly_delta_usd=Decimal("75"),
            estimated_hourly_delta_usd=Decimal("0.1"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="deny-release-1",
        ),
    )
    assert gate_result.approval is not None
    assert gate_result.decision.reservation_active is True
    assert gate_result.decision.reserved_allocation_usd == Decimal("75.0000")

    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    approval, decision = await service.deny_request(
        tenant_id=tenant.id,
        approval_id=gate_result.approval.id,
        reviewer=reviewer,
        notes="denied by policy review",
    )

    assert approval.status == EnforcementApprovalStatus.DENIED
    assert decision.reservation_active is False
    assert decision.reserved_allocation_usd == Decimal("0")
    assert decision.reserved_credit_usd == Decimal("0")


@pytest.mark.asyncio
async def test_create_credit_grant_rejects_past_expiry(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)

    with pytest.raises(HTTPException) as exc:
        await service.create_credit_grant(
            tenant_id=tenant.id,
            actor_id=uuid4(),
            scope_key="default",
            total_amount_usd=Decimal("10"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            reason="expired fixture",
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_replay(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, approval, decision = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-replay-1",
    )

    service = EnforcementService(db)
    consumed_approval, consumed_decision = await service.consume_approval_token(
        tenant_id=tenant.id,
        approval_token=token,
        actor_id=actor_id,
        expected_source=EnforcementSource.TERRAFORM,
        expected_environment="prod",
        expected_request_fingerprint=decision.request_fingerprint,
        expected_resource_reference=decision.resource_reference,
    )
    assert consumed_approval.id == approval.id
    assert consumed_decision.id == decision.id
    assert consumed_approval.approval_token_consumed_at is not None

    with pytest.raises(HTTPException) as replay_exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=token,
            actor_id=actor_id,
        )
    assert replay_exc.value.status_code == 409
    assert "replay" in str(replay_exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_replay_records_metrics(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-replay-metrics-1",
    )
    token_events = _FakeCounter()
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL",
        token_events,
    )

    service = EnforcementService(db)
    await service.consume_approval_token(
        tenant_id=tenant.id,
        approval_token=token,
        actor_id=actor_id,
    )
    with pytest.raises(HTTPException):
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=token,
            actor_id=actor_id,
        )

    event_calls = [labels.get("event") for labels, _ in token_events.calls]
    assert "consumed" in event_calls
    assert "replay_detected" in event_calls


@pytest.mark.asyncio
async def test_consume_approval_token_accepts_rotated_fallback_secret(
    db, monkeypatch
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    old_secret = "old-approval-signing-secret-12345678901234567890"
    new_secret = "new-approval-signing-secret-12345678901234567890"

    def _settings(
        secret: str,
        fallback: list[str] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            SUPABASE_JWT_SECRET=secret,
            API_URL="https://api.valdrix.local",
            JWT_SIGNING_KID="",
            ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS=list(fallback or []),
        )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: _settings(old_secret),
    )
    token, approval, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-rotation-fallback-1",
    )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: _settings(new_secret, [old_secret]),
    )
    service = EnforcementService(db)
    consumed_approval, _ = await service.consume_approval_token(
        tenant_id=tenant.id,
        approval_token=token,
        actor_id=actor_id,
    )
    assert consumed_approval.id == approval.id
    assert consumed_approval.approval_token_consumed_at is not None


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_rotated_secret_without_fallback(
    db, monkeypatch
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    old_secret = "old-approval-signing-secret-09876543210987654321"
    new_secret = "new-approval-signing-secret-09876543210987654321"

    def _settings(
        secret: str,
        fallback: list[str] | None = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            SUPABASE_JWT_SECRET=secret,
            API_URL="https://api.valdrix.local",
            JWT_SIGNING_KID="",
            ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS=list(fallback or []),
        )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: _settings(old_secret),
    )
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-rotation-no-fallback-1",
    )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: _settings(new_secret),
    )
    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=token,
            actor_id=actor_id,
        )
    assert exc.value.status_code == 401
    assert "invalid approval token" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_tampered_payload(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-tamper-1",
    )
    header, payload, signature = token.split(".")
    decoded_payload = json.loads(base64.urlsafe_b64decode(payload + "==").decode())
    decoded_payload["resource_reference"] = "module.hijack.aws_iam_role.admin"
    tampered_payload = (
        base64.urlsafe_b64encode(json.dumps(decoded_payload).encode()).decode().rstrip("=")
    )
    tampered_token = f"{header}.{tampered_payload}.{signature}"

    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=tampered_token,
            actor_id=actor_id,
        )
    assert exc.value.status_code == 401
    assert "invalid approval token" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_wrong_tenant(db) -> None:
    tenant_a = await _seed_tenant(db)
    tenant_b = await _seed_tenant(db)
    actor_id = uuid4()
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant_a.id,
        actor_id=actor_id,
        idempotency_key="consume-wrong-tenant-1",
    )

    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant_b.id,
            approval_token=token,
            actor_id=actor_id,
        )
    assert exc.value.status_code == 403
    assert "tenant mismatch" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_expected_binding_mismatch(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-binding-mismatch-1",
    )

    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=token,
            actor_id=actor_id,
            expected_resource_reference="module.other.aws_db_instance.main",
        )
    assert exc.value.status_code == 409
    assert "resource reference mismatch" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_concurrency_single_use(db, async_engine) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, _, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-concurrency-1",
    )

    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def consume_once() -> int:
        async with session_maker() as session:
            service = EnforcementService(session)
            try:
                await service.consume_approval_token(
                    tenant_id=tenant.id,
                    approval_token=token,
                    actor_id=actor_id,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    statuses = await asyncio.gather(*[consume_once() for _ in range(6)])
    assert statuses.count(200) == 1
    assert statuses.count(409) == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "expected_decision", "expected_reason", "expect_approval"),
    [
        (
            EnforcementMode.SHADOW,
            EnforcementDecisionType.ALLOW,
            "shadow_mode_fail_open",
            False,
        ),
        (
            EnforcementMode.SOFT,
            EnforcementDecisionType.REQUIRE_APPROVAL,
            "soft_mode_fail_safe_escalation",
            True,
        ),
        (
            EnforcementMode.HARD,
            EnforcementDecisionType.DENY,
            "hard_mode_fail_closed",
            False,
        ),
    ],
)
async def test_resolve_fail_safe_gate_timeout_mode_behavior(
    db,
    mode: EnforcementMode,
    expected_decision: EnforcementDecisionType,
    expected_reason: str,
    expect_approval: bool,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    service = EnforcementService(db)

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=mode,
        k8s_admission_mode=mode,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )

    result = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.eks.aws_eks_cluster.main",
            estimated_monthly_delta_usd=Decimal("100"),
            estimated_hourly_delta_usd=Decimal("0.1"),
            metadata={"resource_type": "aws_eks_cluster"},
            idempotency_key=f"failsafe-timeout-{mode.value}",
        ),
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )

    assert result.decision.decision == expected_decision
    assert "gate_timeout" in (result.decision.reason_codes or [])
    assert expected_reason in (result.decision.reason_codes or [])
    assert result.decision.reservation_active is False
    assert result.decision.reserved_allocation_usd == Decimal("0")
    assert result.decision.reserved_credit_usd == Decimal("0")
    assert (result.approval is not None) is expect_approval


@pytest.mark.asyncio
async def test_resolve_fail_safe_gate_idempotency_reuses_existing_decision(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    service = EnforcementService(db)

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.HARD,
        k8s_admission_mode=EnforcementMode.HARD,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )

    gate_input = GateInput(
        project_id="default",
        environment="prod",
        action="terraform.apply",
        resource_reference="module.rds.aws_db_instance.main",
        estimated_monthly_delta_usd=Decimal("80"),
        estimated_hourly_delta_usd=Decimal("0.09"),
        metadata={"resource_type": "aws_db_instance"},
        idempotency_key="failsafe-idem-1",
    )

    first = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=gate_input,
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )
    second = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=gate_input,
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )

    assert first.decision.id == second.decision.id
    count = (
        await db.execute(
            select(func.count())
            .select_from(EnforcementDecision)
            .where(EnforcementDecision.tenant_id == tenant.id)
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_approve_request_member_denied_without_scim_permission(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="member-denied-no-scim-1",
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    with pytest.raises(HTTPException) as exc:
        await service.approve_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="attempt without permission",
        )
    assert exc.value.status_code == 403
    assert APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD in str(exc.value.detail)


@pytest.mark.asyncio
async def test_approve_request_member_allowed_with_scim_prod_permission(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="member-allowed-scim-prod-1",
    )
    member_id = uuid4()
    await _seed_member_scim_permission(
        db=db,
        tenant_id=tenant.id,
        member_id=member_id,
        permissions=[APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD],
        scim_enabled=True,
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=member_id,
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    approval, decision, token, _ = await service.approve_request(
        tenant_id=tenant.id,
        approval_id=gate.approval.id,
        reviewer=reviewer,
        notes="approved via scim prod permission",
    )
    assert approval.status == EnforcementApprovalStatus.APPROVED
    assert isinstance(token, str) and token
    assert decision.approval_token_issued is True


@pytest.mark.asyncio
async def test_approve_request_member_allowed_with_scim_nonprod_permission(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="member-allowed-scim-nonprod-1",
    )
    member_id = uuid4()
    await _seed_member_scim_permission(
        db=db,
        tenant_id=tenant.id,
        member_id=member_id,
        permissions=[APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD],
        scim_enabled=True,
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=member_id,
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    approval, _, _, _ = await service.approve_request(
        tenant_id=tenant.id,
        approval_id=gate.approval.id,
        reviewer=reviewer,
        notes="approved via scim nonprod permission",
    )
    assert approval.status == EnforcementApprovalStatus.APPROVED


@pytest.mark.asyncio
async def test_approve_request_member_denied_when_scim_disabled_even_with_mapping(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="member-denied-scim-disabled-1",
    )
    member_id = uuid4()
    await _seed_member_scim_permission(
        db=db,
        tenant_id=tenant.id,
        member_id=member_id,
        permissions=[APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD],
        scim_enabled=False,
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=member_id,
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    with pytest.raises(HTTPException) as exc:
        await service.approve_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="attempt while scim disabled",
        )
    assert exc.value.status_code == 403
    assert APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD in str(exc.value.detail)


@pytest.mark.asyncio
async def test_reconcile_reservation_releases_and_records_drift(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-reservation-1",
    )
    service = EnforcementService(db)

    result = await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="monthly close reconciliation",
    )

    assert result.decision.id == gate.decision.id
    assert result.decision.reservation_active is False
    assert result.decision.reserved_allocation_usd == Decimal("0")
    assert result.decision.reserved_credit_usd == Decimal("0")
    assert result.released_reserved_usd == Decimal("75.0000")
    assert result.actual_monthly_delta_usd == Decimal("80.0000")
    assert result.drift_usd == Decimal("5.0000")
    assert result.status == "overage"
    assert "reservation_reconciled" in (result.decision.reason_codes or [])
    assert "reservation_reconciliation_drift" in (result.decision.reason_codes or [])


@pytest.mark.asyncio
async def test_reconcile_reservation_records_metrics(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-reservation-metrics-1",
    )
    reconciliations = _FakeCounter()
    drift = _FakeCounter()
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL",
        reconciliations,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_RESERVATION_DRIFT_USD_TOTAL",
        drift,
    )

    service = EnforcementService(db)
    await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="metrics check",
    )

    assert ({"trigger": "manual", "status": "overage"}, 1.0) in reconciliations.calls
    assert ({"direction": "overage"}, 5.0) in drift.calls


@pytest.mark.asyncio
async def test_reconcile_reservation_rejects_when_not_active(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-reservation-inactive-1",
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    await service.deny_request(
        tenant_id=tenant.id,
        approval_id=gate.approval.id,
        reviewer=reviewer,
        notes="force inactive before reconcile",
    )

    with pytest.raises(HTTPException) as exc:
        await service.reconcile_reservation(
            tenant_id=tenant.id,
            decision_id=gate.decision.id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("0"),
            notes="should fail",
        )
    assert exc.value.status_code == 409
    assert "not active" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_reconcile_overdue_reservations_releases_only_stale(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    stale_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-overdue-stale-1",
    )
    fresh_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-overdue-fresh-1",
    )

    stale_decision = (
        await db.execute(
            select(EnforcementDecision).where(
                EnforcementDecision.id == stale_gate.decision.id
            )
        )
    ).scalar_one()
    stale_decision.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db.commit()

    service = EnforcementService(db)
    summary = await service.reconcile_overdue_reservations(
        tenant_id=tenant.id,
        actor_id=actor_id,
        older_than_seconds=3600,
        limit=200,
    )

    assert summary.released_count == 1
    assert stale_gate.decision.id in summary.decision_ids
    assert fresh_gate.decision.id not in summary.decision_ids
    assert summary.total_released_usd == Decimal("75.0000")


@pytest.mark.asyncio
async def test_list_reconciliation_exceptions_returns_only_drift(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    drift_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-exception-drift-1",
    )
    matched_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-exception-matched-1",
    )

    service = EnforcementService(db)
    await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=drift_gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="drift case",
    )
    await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=matched_gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("75"),
        notes="matched case",
    )

    exceptions = await service.list_reconciliation_exceptions(
        tenant_id=tenant.id,
        limit=50,
    )

    assert len(exceptions) == 1
    assert exceptions[0].decision.id == drift_gate.decision.id
    assert exceptions[0].status == "overage"
    assert exceptions[0].drift_usd == Decimal("5.0000")


@pytest.mark.asyncio
async def test_build_export_bundle_reconciles_counts_and_is_deterministic(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()

    first_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="export-bundle-1",
    )
    second_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=True,
        idempotency_key="export-bundle-2",
    )
    assert first_gate.approval is not None
    assert second_gate.approval is not None

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=1)

    service = EnforcementService(db)
    first_bundle = await service.build_export_bundle(
        tenant_id=tenant.id,
        window_start=window_start,
        window_end=window_end,
        max_rows=1000,
    )
    second_bundle = await service.build_export_bundle(
        tenant_id=tenant.id,
        window_start=window_start,
        window_end=window_end,
        max_rows=1000,
    )

    assert first_bundle.decision_count_db == 2
    assert first_bundle.decision_count_exported == 2
    assert first_bundle.approval_count_db == 2
    assert first_bundle.approval_count_exported == 2
    assert first_bundle.parity_ok is True

    assert first_bundle.decisions_sha256 == second_bundle.decisions_sha256
    assert first_bundle.approvals_sha256 == second_bundle.approvals_sha256

    decision_reader = csv.reader(io.StringIO(first_bundle.decisions_csv))
    approval_reader = csv.reader(io.StringIO(first_bundle.approvals_csv))
    decision_rows = list(decision_reader)
    approval_rows = list(approval_reader)
    assert len(decision_rows) == first_bundle.decision_count_exported + 1
    assert len(approval_rows) == first_bundle.approval_count_exported + 1


@pytest.mark.asyncio
async def test_build_export_bundle_rejects_window_above_max_rows(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()

    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="export-bundle-limit-1",
    )
    assert gate.approval is not None

    now = datetime.now(timezone.utc)
    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.build_export_bundle(
            tenant_id=tenant.id,
            window_start=now - timedelta(days=1),
            window_end=now + timedelta(days=1),
            max_rows=0,
        )

    assert exc.value.status_code == 422
    assert "max_rows" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_evaluate_gate_appends_immutable_decision_ledger_entry(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("250"),
        active=True,
    )

    payload = GateInput(
        project_id="default",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.vpc.aws_vpc.main",
        estimated_monthly_delta_usd=Decimal("50"),
        estimated_hourly_delta_usd=Decimal("0.07"),
        metadata={"resource_type": "aws_vpc"},
        idempotency_key="ledger-idempotency-1",
    )

    first = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )
    second = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )

    assert first.decision.id == second.decision.id

    rows = await db.execute(
        select(EnforcementDecisionLedger)
        .where(EnforcementDecisionLedger.tenant_id == tenant.id)
        .order_by(EnforcementDecisionLedger.recorded_at.asc())
    )
    ledger_entries = list(rows.scalars().all())
    assert len(ledger_entries) == 1
    entry = ledger_entries[0]
    assert entry.decision_id == first.decision.id
    assert entry.decision == first.decision.decision
    assert entry.request_fingerprint == first.decision.request_fingerprint
    assert len(entry.request_payload_sha256) == 64
    assert len(entry.response_payload_sha256) == 64
    entry_id = entry.id

    entry.reason_codes = ["tamper_attempt"]
    with pytest.raises(Exception) as update_exc:
        await db.commit()
    assert "append-only" in str(update_exc.value).lower()
    await db.rollback()

    persisted = (
        await db.execute(
            select(EnforcementDecisionLedger).where(
                EnforcementDecisionLedger.id == entry_id
            )
        )
    ).scalar_one()
    assert "tamper_attempt" not in (persisted.reason_codes or [])

    await db.delete(persisted)
    with pytest.raises(Exception) as delete_exc:
        await db.commit()
    assert "append-only" in str(delete_exc.value).lower()
    await db.rollback()


@pytest.mark.asyncio
async def test_resolve_fail_safe_gate_appends_decision_ledger_entry(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.HARD,
        k8s_admission_mode=EnforcementMode.HARD,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )

    result = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.eks.aws_eks_cluster.main",
            estimated_monthly_delta_usd=Decimal("80"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_eks_cluster"},
            idempotency_key="ledger-failsafe-1",
        ),
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.100"},
    )

    ledger_row = (
        await db.execute(
            select(EnforcementDecisionLedger).where(
                EnforcementDecisionLedger.decision_id == result.decision.id
            )
        )
    ).scalar_one()
    assert ledger_row.decision_id == result.decision.id
    assert ledger_row.decision == EnforcementDecisionType.DENY
    assert "gate_timeout" in (ledger_row.reason_codes or [])
