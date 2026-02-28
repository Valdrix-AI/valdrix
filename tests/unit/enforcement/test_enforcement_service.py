from __future__ import annotations

import asyncio
import base64
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.enforcement.domain.service as enforcement_service_module
from app.models.enforcement import (
    EnforcementApprovalStatus,
    EnforcementCreditGrant,
    EnforcementCreditPoolType,
    EnforcementCreditReservationAllocation,
    EnforcementDecision,
    EnforcementDecisionLedger,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementSource,
)
from app.models.cloud import CloudAccount, CostRecord
from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import Tenant, User, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.enforcement.domain.policy_document import (
    POLICY_DOCUMENT_SCHEMA_VERSION,
    PolicyDocument,
    canonical_policy_document_payload,
    policy_document_sha256,
)
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


async def _seed_daily_cost_history(
    db: AsyncSession,
    *,
    tenant_id,
    provider: str,
    daily_costs: list[tuple[date, Decimal]],
) -> CloudAccount:
    account = CloudAccount(
        id=uuid4(),
        tenant_id=tenant_id,
        provider=provider,
        name=f"{provider}-cost-account",
        is_production=True,
        criticality="high",
        is_active=True,
    )
    db.add(account)
    await db.flush()

    for idx, (record_day, cost) in enumerate(daily_costs):
        db.add(
            CostRecord(
                id=uuid4(),
                tenant_id=tenant_id,
                account_id=account.id,
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
                resource_id=f"seed-{record_day.isoformat()}-{idx}",
                usage_amount=Decimal("1"),
                usage_unit="Hrs",
                canonical_charge_category="compute",
                canonical_charge_subcategory="instance",
                canonical_mapping_version="focus-1.3-v1",
                cost_usd=cost.quantize(Decimal("0.0001")),
                amount_raw=cost.quantize(Decimal("0.0001")),
                currency="USD",
                carbon_kg=None,
                is_preliminary=False,
                cost_status="FINAL",
                reconciliation_run_id=None,
                ingestion_metadata=None,
                tags=None,
                attribution_id=None,
                allocated_to=None,
                recorded_at=record_day,
                timestamp=datetime(
                    record_day.year,
                    record_day.month,
                    record_day.day,
                    12,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
            )
        )

    await db.commit()
    return account


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
    approval_routing_rules: list[dict[str, object]] | None = None,
    enforce_prod_requester_reviewer_separation: bool = True,
    enforce_nonprod_requester_reviewer_separation: bool = False,
):
    service = EnforcementService(db)
    await service.update_policy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=require_approval_for_prod,
        require_approval_for_nonprod=require_approval_for_nonprod,
        enforce_prod_requester_reviewer_separation=enforce_prod_requester_reviewer_separation,
        enforce_nonprod_requester_reviewer_separation=enforce_nonprod_requester_reviewer_separation,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
        approval_routing_rules=approval_routing_rules,
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
async def test_update_policy_materializes_policy_document_contract_and_hash(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)

    policy = await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.HARD,
        terraform_mode_prod=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.SHADOW,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.HARD,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=True,
        require_approval_for_nonprod=True,
        plan_monthly_ceiling_usd=Decimal("1500"),
        enterprise_monthly_ceiling_usd=Decimal("2500"),
        auto_approve_below_monthly_usd=Decimal("10"),
        hard_deny_above_monthly_usd=Decimal("3000"),
        default_ttl_seconds=1200,
        approval_routing_rules=[
            {
                "rule_id": "policy-doc-hash-test",
                "enabled": True,
                "environments": ["prod"],
                "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                "allowed_reviewer_roles": ["owner", "admin"],
            }
        ],
    )

    assert policy.policy_document_schema_version == POLICY_DOCUMENT_SCHEMA_VERSION
    assert len(policy.policy_document_sha256) == 64

    parsed = PolicyDocument.model_validate(policy.policy_document)
    canonical = canonical_policy_document_payload(parsed)
    assert policy.policy_document_sha256 == policy_document_sha256(canonical)
    assert parsed.mode_matrix.terraform_default == EnforcementMode.HARD
    assert parsed.mode_matrix.terraform_nonprod == EnforcementMode.SHADOW
    assert parsed.execution.default_ttl_seconds == 1200


@pytest.mark.asyncio
async def test_update_policy_uses_policy_document_as_authoritative_contract(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)

    policy = await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.SOFT,
        terraform_mode_nonprod=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        plan_monthly_ceiling_usd=Decimal("1"),
        enterprise_monthly_ceiling_usd=Decimal("2"),
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("10"),
        default_ttl_seconds=900,
        policy_document={
            "schema_version": POLICY_DOCUMENT_SCHEMA_VERSION,
            "mode_matrix": {
                "terraform_default": "hard",
                "terraform_prod": "hard",
                "terraform_nonprod": "shadow",
                "k8s_admission_default": "shadow",
                "k8s_admission_prod": "hard",
                "k8s_admission_nonprod": "soft",
            },
            "approval": {
                "require_approval_prod": True,
                "require_approval_nonprod": True,
                "enforce_prod_requester_reviewer_separation": True,
                "enforce_nonprod_requester_reviewer_separation": False,
                "routing_rules": [
                    {
                        "rule_id": "prod-route",
                        "enabled": True,
                        "environments": ["PROD"],
                        "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                        "allowed_reviewer_roles": ["OWNER", "MEMBER"],
                    }
                ],
            },
            "entitlements": {
                "plan_monthly_ceiling_usd": "111.1",
                "enterprise_monthly_ceiling_usd": "222.2",
                "auto_approve_below_monthly_usd": "5",
                "hard_deny_above_monthly_usd": "500",
            },
            "execution": {"default_ttl_seconds": 1800},
        },
    )

    assert policy.terraform_mode == EnforcementMode.HARD
    assert policy.terraform_mode_nonprod == EnforcementMode.SHADOW
    assert policy.k8s_admission_mode == EnforcementMode.SHADOW
    assert policy.k8s_admission_mode_prod == EnforcementMode.HARD
    assert policy.require_approval_for_prod is True
    assert policy.require_approval_for_nonprod is True
    assert policy.plan_monthly_ceiling_usd == Decimal("111.1000")
    assert policy.enterprise_monthly_ceiling_usd == Decimal("222.2000")
    assert policy.auto_approve_below_monthly_usd == Decimal("5.0000")
    assert policy.hard_deny_above_monthly_usd == Decimal("500.0000")
    assert policy.default_ttl_seconds == 1800
    assert policy.approval_routing_rules[0]["allowed_reviewer_roles"] == [
        "owner",
        "member",
    ]
    assert policy.approval_routing_rules[0]["environments"] == ["prod"]


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
    assert first.decision.decision == second.decision.decision
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
async def test_evaluate_gate_integrityerror_replays_existing_idempotent_decision(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)
    payload = GateInput(
        project_id="proj-race",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.ec2.aws_instance.race",
        estimated_monthly_delta_usd=Decimal("15"),
        estimated_hourly_delta_usd=Decimal("0.02"),
        metadata={"resource_type": "aws_instance"},
        idempotency_key="idem-race-replay-1",
    )

    seeded = await seed_service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )
    existing_decision_id = seeded.decision.id
    existing_decision_stub = SimpleNamespace(
        id=existing_decision_id,
        decision=seeded.decision.decision,
    )

    service = EnforcementService(db)
    idem_calls: list[str] = []
    approval_calls: list[object] = []

    async def _fake_get_decision_by_idempotency(**_kwargs):
        idem_calls.append("call")
        if len(idem_calls) < 3:
            return None
        return existing_decision_stub

    async def _fake_get_approval_by_decision(decision_id):
        approval_calls.append(decision_id)
        return None

    async def _noop_lock(**_kwargs):
        return None

    monkeypatch.setattr(service, "_get_decision_by_idempotency", _fake_get_decision_by_idempotency)
    monkeypatch.setattr(service, "_get_approval_by_decision", _fake_get_approval_by_decision)
    monkeypatch.setattr(service, "_acquire_gate_evaluation_lock", _noop_lock)

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )

    assert result.decision.id == existing_decision_id
    assert result.approval is None
    assert len(idem_calls) == 3  # pre-check, post-lock recheck, IntegrityError replay fallback
    assert approval_calls == [existing_decision_id]


@pytest.mark.asyncio
async def test_evaluate_gate_integrityerror_reraises_when_replay_lookup_missing(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)
    payload = GateInput(
        project_id="proj-race-miss",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.ec2.aws_instance.race-miss",
        estimated_monthly_delta_usd=Decimal("16"),
        estimated_hourly_delta_usd=Decimal("0.021"),
        metadata={"resource_type": "aws_instance"},
        idempotency_key="idem-race-reraise-1",
    )

    # Seed a real decision so the duplicate insert triggers a database IntegrityError.
    await seed_service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
    )

    service = EnforcementService(db)
    idem_calls: list[str] = []

    async def _always_miss_idempotency(**_kwargs):
        idem_calls.append("call")
        return None

    async def _noop_lock(**_kwargs):
        return None

    monkeypatch.setattr(service, "_get_decision_by_idempotency", _always_miss_idempotency)
    monkeypatch.setattr(service, "_acquire_gate_evaluation_lock", _noop_lock)

    with pytest.raises(enforcement_service_module.IntegrityError):
        await service.evaluate_gate(
            tenant_id=tenant.id,
            actor_id=actor_id,
            source=EnforcementSource.TERRAFORM,
            gate_input=payload,
        )

    assert len(idem_calls) == 3  # pre-check, post-lock recheck, replay lookup after rollback


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
async def test_evaluate_gate_computed_context_populates_decision_and_ledger(
    db,
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)

    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    daily_costs = [(date(2026, 2, day), Decimal("100")) for day in range(1, 20)]
    daily_costs.append((date(2026, 2, 20), Decimal("300")))
    await _seed_daily_cost_history(
        db,
        tenant_id=tenant.id,
        provider="aws",
        daily_costs=daily_costs,
    )

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10000"),
        active=True,
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.destroy",
            resource_reference="module.db.aws_db_instance.main",
            estimated_monthly_delta_usd=Decimal("1500"),
            estimated_hourly_delta_usd=Decimal("2.08"),
            metadata={"resource_type": "aws_db_instance", "criticality": "critical"},
            idempotency_key="computed-context-1",
        ),
    )

    assert result.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert result.approval is not None
    assert result.decision.burn_rate_daily_usd == Decimal("110.0000")
    assert result.decision.forecast_eom_usd == Decimal("3080.0000")
    assert result.decision.risk_class == "high"
    assert int(result.decision.risk_score or 0) >= 6
    assert result.decision.anomaly_signal is True
    assert result.decision.policy_document_schema_version == "valdrix.enforcement.policy.v1"
    assert len(result.decision.policy_document_sha256) == 64

    payload = result.decision.response_payload or {}
    context = payload.get("computed_context")
    assert isinstance(context, dict)
    assert context.get("burn_rate_daily_usd") == "110.0000"
    assert context.get("forecast_eom_usd") == "3080.0000"
    assert context.get("mtd_spend_usd") == "2200.0000"
    assert context.get("anomaly_signal") is True
    assert context.get("anomaly_kind") == "spike"
    assert context.get("anomaly_delta_usd") == "200.0000"
    assert context.get("anomaly_percent") == "200.00"
    assert context.get("risk_class") == "high"
    assert context.get("month_elapsed_days") == 20
    assert context.get("month_total_days") == 28
    assert context.get("observed_cost_days") == 20
    assert context.get("data_source_mode") == "final"

    metadata = (result.decision.request_payload or {}).get("metadata") or {}
    assert metadata.get("risk_level") == "high"
    assert metadata.get("computed_risk_class") == "high"
    assert int(metadata.get("computed_risk_score", 0)) >= 6

    ledger_row = (
        await db.execute(
            select(EnforcementDecisionLedger).where(
                EnforcementDecisionLedger.decision_id == result.decision.id
            )
        )
    ).scalar_one()
    assert ledger_row.burn_rate_daily_usd == Decimal("110.0000")
    assert ledger_row.forecast_eom_usd == Decimal("3080.0000")
    assert ledger_row.risk_class == "high"
    assert int(ledger_row.risk_score or 0) >= 6
    assert ledger_row.anomaly_signal is True
    assert ledger_row.policy_document_schema_version == "valdrix.enforcement.policy.v1"
    assert len(ledger_row.policy_document_sha256) == 64
    assert ledger_row.policy_document_sha256 == result.decision.policy_document_sha256


@pytest.mark.asyncio
async def test_evaluate_gate_computed_context_defaults_when_cost_history_missing(
    db,
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)

    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.vpc.aws_vpc.main",
            estimated_monthly_delta_usd=Decimal("12"),
            estimated_hourly_delta_usd=Decimal("0.02"),
            metadata={"resource_type": "aws_vpc"},
            idempotency_key="computed-context-no-history-1",
        ),
    )

    assert result.decision.decision == EnforcementDecisionType.ALLOW
    assert result.decision.burn_rate_daily_usd == Decimal("0.0000")
    assert result.decision.forecast_eom_usd == Decimal("0.0000")
    assert result.decision.risk_class == "low"
    assert result.decision.anomaly_signal is False

    payload = result.decision.response_payload or {}
    context = payload.get("computed_context")
    assert isinstance(context, dict)
    assert context.get("data_source_mode") == "none"
    assert context.get("burn_rate_daily_usd") == "0.0000"
    assert context.get("forecast_eom_usd") == "0.0000"
    assert context.get("mtd_spend_usd") == "0.0000"
    assert context.get("observed_cost_days") == 0
    assert context.get("latest_cost_date") is None


@pytest.mark.asyncio
async def test_evaluate_gate_computed_context_detects_new_spend_when_baseline_is_zero(
    db,
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)

    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await _seed_daily_cost_history(
        db,
        tenant_id=tenant.id,
        provider="aws",
        daily_costs=[(date(2026, 2, 20), Decimal("150"))],
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.lambda.aws_lambda_function.new-service",
            estimated_monthly_delta_usd=Decimal("20"),
            estimated_hourly_delta_usd=Decimal("0.03"),
            metadata={"resource_type": "aws_lambda_function"},
            idempotency_key="computed-context-new-spend-1",
        ),
    )

    context = (result.decision.response_payload or {}).get("computed_context")
    assert isinstance(context, dict)
    assert result.decision.anomaly_signal is True
    assert context.get("anomaly_signal") is True
    assert context.get("anomaly_kind") == "new_spend"
    assert context.get("anomaly_percent") is None
    assert context.get("anomaly_delta_usd") == "150.0000"
    assert context.get("data_source_mode") == "final"


@pytest.mark.asyncio
async def test_evaluate_gate_computed_context_marks_unavailable_on_cost_query_failure(
    db,
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)

    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()
    warning_calls: list[tuple[str, dict[str, object]]] = []

    async def _raise_cost_query(**_kwargs):
        raise RuntimeError("cost backend unavailable")

    def _capture_warning(event: str, **kwargs):
        warning_calls.append((event, dict(kwargs)))

    monkeypatch.setattr(service, "_load_daily_cost_totals", _raise_cost_query)
    monkeypatch.setattr(enforcement_service_module.logger, "warning", _capture_warning)

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.vpc.aws_vpc.main",
            estimated_monthly_delta_usd=Decimal("12"),
            estimated_hourly_delta_usd=Decimal("0.02"),
            metadata={"resource_type": "aws_vpc"},
            idempotency_key="computed-context-unavailable-1",
        ),
    )

    context = (result.decision.response_payload or {}).get("computed_context")
    assert isinstance(context, dict)
    assert context.get("data_source_mode") == "unavailable"
    assert context.get("anomaly_signal") is False
    assert context.get("anomaly_kind") is None
    assert context.get("burn_rate_daily_usd") == "0.0000"
    assert context.get("forecast_eom_usd") == "0.0000"
    assert warning_calls
    assert warning_calls[0][0] == "enforcement_computed_context_unavailable"
    assert warning_calls[0][1]["tenant_id"] == str(tenant.id)
    assert warning_calls[0][1]["error_type"] == "RuntimeError"


@pytest.mark.asyncio
async def test_evaluate_gate_computed_context_snapshot_metadata_stable_across_runs(
    db,
    monkeypatch,
) -> None:
    fixed_now = datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)

    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    daily_costs = [(date(2026, 2, day), Decimal("50")) for day in range(1, 21)]
    await _seed_daily_cost_history(
        db,
        tenant_id=tenant.id,
        provider="aws",
        daily_costs=daily_costs,
    )

    gate_input = GateInput(
        project_id="default",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.vpc.aws_vpc.main",
        estimated_monthly_delta_usd=Decimal("10"),
        estimated_hourly_delta_usd=Decimal("0.01"),
        metadata={"resource_type": "aws_vpc"},
        dry_run=True,
    )

    first = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(**{**gate_input.__dict__, "idempotency_key": "context-stable-1"}),
    )
    second = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(**{**gate_input.__dict__, "idempotency_key": "context-stable-2"}),
    )

    first_context = (first.decision.response_payload or {}).get("computed_context")
    second_context = (second.decision.response_payload or {}).get("computed_context")
    assert isinstance(first_context, dict)
    assert isinstance(second_context, dict)

    stable_keys = [
        "month_start",
        "month_end",
        "month_elapsed_days",
        "month_total_days",
        "observed_cost_days",
        "latest_cost_date",
        "mtd_spend_usd",
        "burn_rate_daily_usd",
        "forecast_eom_usd",
        "data_source_mode",
    ]
    for key in stable_keys:
        assert first_context.get(key) == second_context.get(key), key


@pytest.mark.asyncio
async def test_evaluate_gate_enforces_plan_monthly_ceiling_before_budget_waterfall(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        plan_monthly_ceiling_usd=Decimal("50"),
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("500"),
        active=True,
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.plan-cap",
            estimated_monthly_delta_usd=Decimal("60"),
            estimated_hourly_delta_usd=Decimal("0.08"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="plan-ceiling-soft-1",
        ),
    )

    reasons = result.decision.reason_codes or []
    assert result.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert "plan_limit_exceeded" in reasons
    assert "soft_mode_plan_limit_escalation" in reasons
    assert result.decision.reservation_active is False
    assert result.decision.reserved_allocation_usd == Decimal("0")
    assert result.decision.reserved_credit_usd == Decimal("0")
    assert result.approval is not None

    payload = result.decision.response_payload or {}
    assert payload.get("entitlement_reason_code") == "plan_limit_exceeded"
    waterfall = payload.get("entitlement_waterfall")
    assert isinstance(waterfall, list) and waterfall
    assert waterfall[0]["stage"] == "plan_limit"
    assert waterfall[0]["status"] == "fail"
    assert payload.get("plan_headroom_usd") == "50.0000"


@pytest.mark.asyncio
async def test_evaluate_gate_enforces_enterprise_ceiling_after_waterfall_stages(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        enterprise_monthly_ceiling_usd=Decimal("25"),
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("100"),
        active=True,
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.enterprise-cap",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.09"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="enterprise-ceiling-soft-1",
        ),
    )

    reasons = result.decision.reason_codes or []
    assert result.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert "enterprise_ceiling_exceeded" in reasons
    assert "soft_mode_enterprise_ceiling_escalation" in reasons
    assert result.decision.reservation_active is True
    assert result.decision.reserved_allocation_usd == Decimal("25.0000")
    assert result.decision.reserved_credit_usd == Decimal("0.0000")
    assert result.approval is not None

    payload = result.decision.response_payload or {}
    assert payload.get("entitlement_reason_code") == "enterprise_ceiling_exceeded"
    waterfall = payload.get("entitlement_waterfall")
    assert isinstance(waterfall, list)
    assert any(
        stage.get("stage") == "enterprise_ceiling" and stage.get("status") == "fail"
        for stage in waterfall
    )
    assert payload.get("enterprise_headroom_usd") == "25.0000"


@pytest.mark.asyncio
async def test_credit_waterfall_uses_reserved_before_emergency_credit_pools(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("0"),
        active=True,
    )
    reserved_credit = await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("5"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="reserved pool",
    )
    emergency_credit = await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        pool_type=EnforcementCreditPoolType.EMERGENCY,
        scope_key="org",
        total_amount_usd=Decimal("10"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="emergency pool",
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="admission.validate",
            resource_reference="deployments/apps/credit-pool-order",
            estimated_monthly_delta_usd=Decimal("12"),
            estimated_hourly_delta_usd=Decimal("0.02"),
            metadata={"namespace": "apps"},
            idempotency_key="credit-pool-order-1",
        ),
    )

    reasons = result.decision.reason_codes or []
    assert result.decision.decision == EnforcementDecisionType.ALLOW_WITH_CREDITS
    assert result.decision.reserved_allocation_usd == Decimal("0.0000")
    assert result.decision.reserved_credit_usd == Decimal("12.0000")
    assert "credit_waterfall_used" in reasons
    assert "reserved_credit_waterfall_used" in reasons
    assert "emergency_credit_waterfall_used" in reasons

    response_payload = result.decision.response_payload or {}
    assert response_payload.get("reserved_credit_split_usd") == {
        "reserved": "5.0000",
        "emergency": "7.0000",
    }

    refreshed_reserved = (
        await db.execute(
            select(EnforcementCreditGrant).where(
                EnforcementCreditGrant.id == reserved_credit.id
            )
        )
    ).scalar_one()
    refreshed_emergency = (
        await db.execute(
            select(EnforcementCreditGrant).where(
                EnforcementCreditGrant.id == emergency_credit.id
            )
        )
    ).scalar_one()
    assert refreshed_reserved.remaining_amount_usd == Decimal("0.0000")
    assert refreshed_emergency.remaining_amount_usd == Decimal("3.0000")

    allocations = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id == result.decision.id
            )
        )
    ).scalars().all()
    assert len(allocations) == 2


@pytest.mark.asyncio
async def test_credit_waterfall_uses_emergency_only_and_preserves_caller_risk_level(
    db,
) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("0"),
        active=True,
    )
    await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        pool_type=EnforcementCreditPoolType.EMERGENCY,
        scope_key="default",
        total_amount_usd=Decimal("10"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="emergency only pool",
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="admission.validate",
            resource_reference="deployments/apps/emergency-only-credit",
            estimated_monthly_delta_usd=Decimal("3"),
            estimated_hourly_delta_usd=Decimal("0.01"),
            metadata={"namespace": "apps", "risk_level": "manual"},
            idempotency_key="credit-emergency-only-risk-preserve-1",
        ),
    )

    reasons = result.decision.reason_codes or []
    assert result.decision.decision == EnforcementDecisionType.ALLOW_WITH_CREDITS
    assert "credit_waterfall_used" in reasons
    assert "emergency_credit_waterfall_used" in reasons
    assert "reserved_credit_waterfall_used" not in reasons
    assert result.decision.reserved_credit_usd == Decimal("3.0000")

    request_payload = result.decision.request_payload or {}
    metadata_payload = request_payload.get("metadata") or {}
    assert metadata_payload.get("risk_level") == "manual"
    assert metadata_payload.get("computed_risk_class") == result.decision.risk_class
    assert metadata_payload.get("computed_risk_score") == result.decision.risk_score

@pytest.mark.asyncio
async def test_credit_reservation_debits_grants_and_persists_allocation_mapping(db) -> None:
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
    credit = await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="debit check",
    )

    result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="admission.validate",
            resource_reference="deployments/apps/credit-check",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.04"),
            metadata={"namespace": "apps"},
            idempotency_key="credit-debit-map-1",
        ),
    )
    assert result.decision.decision == EnforcementDecisionType.ALLOW_WITH_CREDITS
    assert result.decision.reserved_credit_usd == Decimal("20.0000")

    refreshed_credit = (
        await db.execute(
            select(EnforcementCreditGrant).where(EnforcementCreditGrant.id == credit.id)
        )
    ).scalar_one()
    assert refreshed_credit.remaining_amount_usd == Decimal("80.0000")

    allocations = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id
                == result.decision.id
            )
        )
    ).scalars().all()
    assert len(allocations) == 1
    allocation = allocations[0]
    assert allocation.credit_grant_id == credit.id
    assert allocation.reserved_amount_usd == Decimal("20.0000")
    assert allocation.active is True


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
async def test_deny_request_refunds_reserved_credit_grants(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    credit = await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="deny refund",
    )
    gate_result = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.credit-deny",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="deny-credit-refund-1",
        ),
    )
    assert gate_result.approval is not None
    assert gate_result.decision.reserved_credit_usd == Decimal("20.0000")

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
        notes="blocked",
    )
    assert approval.status == EnforcementApprovalStatus.DENIED
    assert decision.reservation_active is False
    assert decision.reserved_credit_usd == Decimal("0")

    refreshed_credit = (
        await db.execute(
            select(EnforcementCreditGrant).where(EnforcementCreditGrant.id == credit.id)
        )
    ).scalar_one()
    assert refreshed_credit.remaining_amount_usd == Decimal("100.0000")
    assert refreshed_credit.active is True

    allocation_rows = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id == decision.id
            )
        )
    ).scalars().all()
    assert len(allocation_rows) == 1
    allocation = allocation_rows[0]
    assert allocation.active is False
    assert allocation.consumed_amount_usd == Decimal("0.0000")
    assert allocation.released_amount_usd == Decimal("20.0000")


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
async def test_approval_token_claims_include_project_and_hourly_cost_binding(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    project_id = "proj-alpha"
    token, approval, decision = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        project_id=project_id,
        idempotency_key="consume-claim-shape-1",
    )

    service = EnforcementService(db)
    payload = service._decode_approval_token(token)
    assert str(payload.get("token_type")) == "enforcement_approval"
    assert str(payload.get("project_id")) == project_id
    assert str(payload.get("max_monthly_delta_usd")) == str(
        decision.estimated_monthly_delta_usd
    )
    assert str(payload.get("max_hourly_delta_usd")) == str(
        decision.estimated_hourly_delta_usd
    )

    consumed_approval, consumed_decision = await service.consume_approval_token(
        tenant_id=tenant.id,
        approval_token=token,
        actor_id=actor_id,
        expected_project_id=project_id,
    )
    assert consumed_approval.id == approval.id
    assert consumed_decision.id == decision.id


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_project_claim_mismatch(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, approval, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        project_id="proj-bravo",
        idempotency_key="consume-project-mismatch-1",
    )
    service = EnforcementService(db)
    payload = dict(service._decode_approval_token(token))
    payload["project_id"] = "proj-evil"

    settings = enforcement_service_module.get_settings()
    secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
    tampered_token = enforcement_service_module.jwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )
    approval.approval_token_hash = enforcement_service_module.hashlib.sha256(
        tampered_token.encode("utf-8")
    ).hexdigest()
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=tampered_token,
            actor_id=actor_id,
        )
    assert exc.value.status_code == 409
    assert "project binding mismatch" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_consume_approval_token_rejects_hourly_cost_claim_mismatch(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    token, approval, _ = await _issue_approved_token(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        idempotency_key="consume-hourly-mismatch-1",
    )
    service = EnforcementService(db)
    payload = dict(service._decode_approval_token(token))
    payload["max_hourly_delta_usd"] = "999.999999"

    settings = enforcement_service_module.get_settings()
    secret = str(getattr(settings, "SUPABASE_JWT_SECRET", "") or "").strip()
    tampered_token = enforcement_service_module.jwt.encode(
        payload,
        secret,
        algorithm="HS256",
    )
    approval.approval_token_hash = enforcement_service_module.hashlib.sha256(
        tampered_token.encode("utf-8")
    ).hexdigest()
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await service.consume_approval_token(
            tenant_id=tenant.id,
            approval_token=tampered_token,
            actor_id=actor_id,
        )
    assert exc.value.status_code == 409
    assert "cost binding mismatch" in str(exc.value.detail).lower()


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
async def test_resolve_fail_safe_gate_blank_reason_dry_run_and_metadata_branches(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
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
    )

    result = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.ec2.aws_instance.failsafe-dryrun",
            estimated_monthly_delta_usd=Decimal("42"),
            estimated_hourly_delta_usd=Decimal("0.05"),
            metadata={"resource_type": "aws_instance", "risk_level": "manual"},
            idempotency_key="failsafe-blank-reason-dryrun-1",
            dry_run=True,
        ),
        failure_reason_code="   ",
        failure_metadata=None,
    )

    assert result.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert result.approval is None  # dry_run suppresses approval row creation
    assert "gate_evaluation_error" in (result.decision.reason_codes or [])
    assert "soft_mode_fail_safe_escalation" in (result.decision.reason_codes or [])
    assert "dry_run" in (result.decision.reason_codes or [])

    response_payload = result.decision.response_payload or {}
    request_payload = result.decision.request_payload or {}
    metadata_payload = (request_payload.get("metadata") or {})
    assert response_payload.get("fail_safe_trigger") == "gate_evaluation_error"
    assert response_payload.get("fail_safe_details") is None
    assert metadata_payload.get("risk_level") == "manual"  # preserve caller-provided risk level
    assert metadata_payload.get("computed_risk_class") == result.decision.risk_class
    assert metadata_payload.get("computed_risk_score") == result.decision.risk_score


@pytest.mark.asyncio
async def test_resolve_fail_safe_gate_integrityerror_replays_existing_decision(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)
    payload = GateInput(
        project_id="default",
        environment="prod",
        action="terraform.apply",
        resource_reference="module.rds.aws_db_instance.failsafe-race",
        estimated_monthly_delta_usd=Decimal("70"),
        estimated_hourly_delta_usd=Decimal("0.08"),
        metadata={"resource_type": "aws_db_instance"},
        idempotency_key="failsafe-replay-race-1",
    )

    seeded = await seed_service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )
    existing_decision_id = seeded.decision.id
    existing_decision_stub = SimpleNamespace(
        id=existing_decision_id,
        decision=seeded.decision.decision,
    )
    existing_approval_stub = (
        SimpleNamespace(id=seeded.approval.id) if seeded.approval is not None else None
    )

    service = EnforcementService(db)
    idem_calls: list[str] = []
    approval_calls: list[object] = []

    async def _fake_get_decision_by_idempotency(**_kwargs):
        idem_calls.append("call")
        if len(idem_calls) == 1:
            return None
        return existing_decision_stub

    async def _fake_get_approval_by_decision(decision_id):
        approval_calls.append(decision_id)
        return existing_approval_stub

    monkeypatch.setattr(service, "_get_decision_by_idempotency", _fake_get_decision_by_idempotency)
    monkeypatch.setattr(service, "_get_approval_by_decision", _fake_get_approval_by_decision)

    result = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )

    assert result.decision.id == existing_decision_id
    assert len(idem_calls) == 2  # pre-check + replay lookup after IntegrityError rollback
    assert approval_calls == [existing_decision_id]


@pytest.mark.asyncio
async def test_resolve_fail_safe_gate_integrityerror_reraises_when_replay_lookup_missing(
    db, monkeypatch
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    seed_service = EnforcementService(db)
    payload = GateInput(
        project_id="default",
        environment="prod",
        action="terraform.apply",
        resource_reference="module.rds.aws_db_instance.failsafe-race-miss",
        estimated_monthly_delta_usd=Decimal("71"),
        estimated_hourly_delta_usd=Decimal("0.081"),
        metadata={"resource_type": "aws_db_instance"},
        idempotency_key="failsafe-rereraise-race-1",
    )

    await seed_service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=payload,
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )

    service = EnforcementService(db)
    idem_calls: list[str] = []

    async def _always_miss_idempotency(**_kwargs):
        idem_calls.append("call")
        return None

    monkeypatch.setattr(service, "_get_decision_by_idempotency", _always_miss_idempotency)

    with pytest.raises(enforcement_service_module.IntegrityError):
        await service.resolve_fail_safe_gate(
            tenant_id=tenant.id,
            actor_id=actor_id,
            source=EnforcementSource.TERRAFORM,
            gate_input=payload,
            failure_reason_code="gate_timeout",
            failure_metadata={"timeout_seconds": "0.01"},
        )

    assert len(idem_calls) == 2  # pre-check + replay lookup after rollback


@pytest.mark.asyncio
async def test_evaluate_gate_uses_terraform_environment_mode_matrix(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    service = EnforcementService(db)

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.SHADOW,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("100"),
        default_ttl_seconds=900,
    )

    prod = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.eks.aws_eks_cluster.prod",
            estimated_monthly_delta_usd=Decimal("250"),
            estimated_hourly_delta_usd=Decimal("0.2"),
            metadata={"resource_type": "aws_eks_cluster"},
            idempotency_key="env-mode-matrix-terraform-prod-1",
        ),
    )
    nonprod = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.eks.aws_eks_cluster.nonprod",
            estimated_monthly_delta_usd=Decimal("250"),
            estimated_hourly_delta_usd=Decimal("0.2"),
            metadata={"resource_type": "aws_eks_cluster"},
            idempotency_key="env-mode-matrix-terraform-nonprod-1",
        ),
    )

    assert prod.decision.decision == EnforcementDecisionType.DENY
    assert "hard_mode_fail_closed" not in (prod.decision.reason_codes or [])
    assert "hard_deny_threshold_exceeded" in (prod.decision.reason_codes or [])
    assert (prod.decision.response_payload or {}).get("mode_scope") == "terraform:prod"

    assert nonprod.decision.decision == EnforcementDecisionType.ALLOW
    assert "shadow_mode_override" in (nonprod.decision.reason_codes or [])
    assert (nonprod.decision.response_payload or {}).get("mode_scope") == "terraform:nonprod"


@pytest.mark.asyncio
async def test_evaluate_gate_uses_k8s_environment_mode_matrix(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    service = EnforcementService(db)

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.SOFT,
        terraform_mode_nonprod=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.HARD,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("100"),
        default_ttl_seconds=900,
    )

    prod = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="admission.validate",
            resource_reference="deployments/apps/prod-api",
            estimated_monthly_delta_usd=Decimal("250"),
            estimated_hourly_delta_usd=Decimal("0.2"),
            metadata={"resource_type": "kubernetes_deployment"},
            idempotency_key="env-mode-matrix-k8s-prod-1",
        ),
    )
    nonprod = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.K8S_ADMISSION,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="admission.validate",
            resource_reference="deployments/apps/nonprod-api",
            estimated_monthly_delta_usd=Decimal("250"),
            estimated_hourly_delta_usd=Decimal("0.2"),
            metadata={"resource_type": "kubernetes_deployment"},
            idempotency_key="env-mode-matrix-k8s-nonprod-1",
        ),
    )

    assert prod.decision.decision == EnforcementDecisionType.DENY
    assert (prod.decision.response_payload or {}).get("mode_scope") == "k8s_admission:prod"
    assert nonprod.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert (nonprod.decision.response_payload or {}).get("mode_scope") == "k8s_admission:nonprod"


@pytest.mark.asyncio
async def test_resolve_fail_safe_gate_respects_environment_mode_matrix(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    service = EnforcementService(db)

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.SHADOW,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("1000"),
        default_ttl_seconds=900,
    )

    prod = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.rds.aws_db_instance.prod",
            estimated_monthly_delta_usd=Decimal("80"),
            estimated_hourly_delta_usd=Decimal("0.09"),
            metadata={"resource_type": "aws_db_instance"},
            idempotency_key="failsafe-env-matrix-prod-1",
        ),
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )
    nonprod = await service.resolve_fail_safe_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.rds.aws_db_instance.nonprod",
            estimated_monthly_delta_usd=Decimal("80"),
            estimated_hourly_delta_usd=Decimal("0.09"),
            metadata={"resource_type": "aws_db_instance"},
            idempotency_key="failsafe-env-matrix-nonprod-1",
        ),
        failure_reason_code="gate_timeout",
        failure_metadata={"timeout_seconds": "0.01"},
    )

    assert prod.decision.decision == EnforcementDecisionType.DENY
    assert "hard_mode_fail_closed" in (prod.decision.reason_codes or [])
    assert (prod.decision.response_payload or {}).get("mode_scope") == "terraform:prod"

    assert nonprod.decision.decision == EnforcementDecisionType.ALLOW
    assert "shadow_mode_fail_open" in (nonprod.decision.reason_codes or [])
    assert (nonprod.decision.response_payload or {}).get("mode_scope") == "terraform:nonprod"


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
    assert "reviewer role" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_approve_request_member_with_scim_permission_requires_explicit_member_route(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="member-scim-needs-route-1",
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

    with pytest.raises(HTTPException) as exc:
        await service.approve_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="member without explicit routing allow-list",
        )
    assert exc.value.status_code == 403
    assert "reviewer role" in str(exc.value.detail).lower()


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
        approval_routing_rules=[
            {
                "rule_id": "allow-member-prod-approver",
                "enabled": True,
                "environments": ["prod"],
                "allowed_reviewer_roles": ["owner", "admin", "member"],
                "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                "require_requester_reviewer_separation": True,
            }
        ],
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
async def test_approve_request_rejects_requester_reviewer_self_approval_for_prod(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="requester-reviewer-self-approval-1",
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=actor_id,
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )

    with pytest.raises(HTTPException) as exc:
        await service.approve_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="self approval should be blocked",
        )
    assert exc.value.status_code == 403
    assert "requester/reviewer separation" in str(exc.value.detail).lower()


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
        approval_routing_rules=[
            {
                "rule_id": "allow-member-nonprod-approver",
                "enabled": True,
                "environments": ["nonprod"],
                "allowed_reviewer_roles": ["owner", "admin", "member"],
                "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
                "require_requester_reviewer_separation": False,
            }
        ],
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
        approval_routing_rules=[
            {
                "rule_id": "allow-member-prod-approver",
                "enabled": True,
                "environments": ["prod"],
                "allowed_reviewer_roles": ["owner", "admin", "member"],
                "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                "require_requester_reviewer_separation": True,
            }
        ],
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
async def test_deny_request_enforces_reviewer_authority(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="deny-request-permission-guard-1",
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    with pytest.raises(HTTPException) as exc:
        await service.deny_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="member without approval authority",
        )
    assert exc.value.status_code == 403


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
    ledger_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(ledger_rows) == 2
    assert ledger_rows[-1].approval_request_id == gate.approval.id
    assert ledger_rows[-1].approval_status == EnforcementApprovalStatus.PENDING
    assert "reservation_reconciled" in (ledger_rows[-1].reason_codes or [])


@pytest.mark.asyncio
async def test_reconcile_reservation_idempotent_replay_with_same_key(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-reservation-idem-seed-1",
    )
    service = EnforcementService(db)

    first = await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="idempotent replay",
        idempotency_key="reconcile-idem-1",
    )
    second = await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="idempotent replay",
        idempotency_key="reconcile-idem-1",
    )

    assert second.decision.id == first.decision.id
    assert second.status == first.status
    assert second.drift_usd == first.drift_usd
    assert second.released_reserved_usd == first.released_reserved_usd
    assert second.reconciled_at == first.reconciled_at
    reconciliation_payload = (second.decision.response_payload or {}).get(
        "reservation_reconciliation",
        {},
    )
    assert reconciliation_payload.get("idempotency_key") == "reconcile-idem-1"
    ledger_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    # Initial gate ledger row + one reconciliation row. Replay must not append.
    assert len(ledger_rows) == 2


@pytest.mark.asyncio
async def test_reconcile_reservation_idempotent_replay_rejects_payload_mismatch(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-reservation-idem-seed-2",
    )
    service = EnforcementService(db)

    await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("80"),
        notes="idempotent replay mismatch",
        idempotency_key="reconcile-idem-2",
    )

    with pytest.raises(HTTPException) as exc:
        await service.reconcile_reservation(
            tenant_id=tenant.id,
            decision_id=gate.decision.id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("81"),
            notes="idempotent replay mismatch",
            idempotency_key="reconcile-idem-2",
        )
    assert exc.value.status_code == 409
    assert "payload mismatch" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_reconcile_reservation_partially_consumes_reserved_credit(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("10"),
        active=True,
    )
    credit = await service.create_credit_grant(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        reason="reconcile partial consume",
    )
    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.credit-reconcile",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="reconcile-credit-partial-1",
        ),
    )
    assert gate.approval is not None
    assert gate.decision.reserved_allocation_usd == Decimal("10.0000")
    assert gate.decision.reserved_credit_usd == Decimal("20.0000")

    result = await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("15"),
        notes="partial credit usage",
    )
    assert result.decision.reservation_active is False
    assert result.status == "savings"
    assert result.drift_usd == Decimal("-15.0000")

    refreshed_credit = (
        await db.execute(
            select(EnforcementCreditGrant).where(EnforcementCreditGrant.id == credit.id)
        )
    ).scalar_one()
    # Reserved 20 at gate-time, then reconcile consumes 5 and releases 15.
    assert refreshed_credit.remaining_amount_usd == Decimal("95.0000")

    allocation = (
        await db.execute(
            select(EnforcementCreditReservationAllocation).where(
                EnforcementCreditReservationAllocation.decision_id == gate.decision.id
            )
        )
    ).scalar_one()
    assert allocation.active is False
    assert allocation.consumed_amount_usd == Decimal("5.0000")
    assert allocation.released_amount_usd == Decimal("15.0000")

    reconciliation_payload = (result.decision.response_payload or {}).get(
        "reservation_reconciliation",
        {},
    )
    assert reconciliation_payload.get("credit_consumed_usd") == "5.0000"
    assert reconciliation_payload.get("credit_released_usd") == "15.0000"
    credit_settlement = reconciliation_payload.get("credit_settlement")
    assert isinstance(credit_settlement, list)
    assert len(credit_settlement) == 1


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
    stale_ledger_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == stale_gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(stale_ledger_rows) == 2
    assert stale_ledger_rows[-1].approval_request_id == stale_gate.approval.id
    assert stale_ledger_rows[-1].approval_status == EnforcementApprovalStatus.PENDING
    assert "reservation_auto_released_sla" in (stale_ledger_rows[-1].reason_codes or [])


@pytest.mark.asyncio
async def test_reconcile_overdue_reservations_records_processed_count_metric(
    db,
    monkeypatch,
) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    stale_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-overdue-metric-stale-1",
    )
    _fresh_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="reconcile-overdue-metric-fresh-1",
    )
    stale_decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == stale_gate.decision.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    stale_decision.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db.commit()

    reconciliations = _FakeCounter()
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_RESERVATION_RECONCILIATIONS_TOTAL",
        reconciliations,
    )
    service = EnforcementService(db)
    summary = await service.reconcile_overdue_reservations(
        tenant_id=tenant.id,
        actor_id=actor_id,
        older_than_seconds=3600,
        limit=200,
    )
    assert summary.released_count == 1
    assert ({"trigger": "auto", "status": "auto_release"}, 1.0) in reconciliations.calls


@pytest.mark.asyncio
async def test_reconcile_reservation_rolls_back_on_credit_settlement_failure(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
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
        reason="rollback test",
    )
    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.rollback-reconcile",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="rollback-reconcile-seed-1",
        ),
    )
    assert gate.approval is not None
    decision_id = gate.decision.id
    await db.execute(
        delete(EnforcementCreditReservationAllocation).where(
            EnforcementCreditReservationAllocation.decision_id == decision_id
        )
    )
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await service.reconcile_reservation(
            tenant_id=tenant.id,
            decision_id=decision_id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("15"),
            notes="should rollback",
            idempotency_key="rollback-reconcile-key-1",
        )
    assert exc.value.status_code == 409
    assert "missing credit reservation allocation" in str(exc.value.detail).lower()

    decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == decision_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert decision.reservation_active is True
    assert decision.reserved_allocation_usd == Decimal("10.0000")
    assert decision.reserved_credit_usd == Decimal("20.0000")
    response_payload = decision.response_payload or {}
    assert "reservation_reconciliation" not in response_payload


@pytest.mark.asyncio
async def test_reconcile_overdue_rolls_back_on_credit_settlement_failure(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
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
        reason="rollback overdue test",
    )
    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.rollback-overdue",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="rollback-overdue-seed-1",
        ),
    )
    assert gate.approval is not None
    decision_id = gate.decision.id
    stale_decision = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == decision_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    stale_decision.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await db.execute(
        delete(EnforcementCreditReservationAllocation).where(
            EnforcementCreditReservationAllocation.decision_id == decision_id
        )
    )
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await service.reconcile_overdue_reservations(
            tenant_id=tenant.id,
            actor_id=actor_id,
            older_than_seconds=3600,
            limit=50,
        )
    assert exc.value.status_code == 409
    assert "missing credit reservation allocation" in str(exc.value.detail).lower()

    refreshed = (
        await db.execute(
            select(EnforcementDecision)
            .where(EnforcementDecision.id == decision_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.reservation_active is True
    assert refreshed.reserved_allocation_usd == Decimal("10.0000")
    assert refreshed.reserved_credit_usd == Decimal("20.0000")
    response_payload = refreshed.response_payload or {}
    assert "auto_reconciliation" not in response_payload


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
async def test_reconciliation_exceptions_include_credit_settlement_diagnostics(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
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
        reason="exceptions diagnostics",
    )
    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.exceptions-credit",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.11"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="exceptions-credit-1",
        ),
    )
    assert gate.approval is not None

    await service.reconcile_reservation(
        tenant_id=tenant.id,
        decision_id=gate.decision.id,
        actor_id=actor_id,
        actual_monthly_delta_usd=Decimal("15"),
        notes="credit diagnostics case",
    )

    exceptions = await service.list_reconciliation_exceptions(
        tenant_id=tenant.id,
        limit=20,
    )
    assert len(exceptions) == 1
    entry = exceptions[0]
    assert entry.decision.id == gate.decision.id
    assert entry.credit_settlement
    settlement = entry.credit_settlement[0]
    assert settlement["consumed_amount_usd"] == "5.0000"
    assert settlement["released_amount_usd"] == "15.0000"


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
    assert first_bundle.policy_lineage_sha256 == second_bundle.policy_lineage_sha256
    assert first_bundle.policy_lineage == second_bundle.policy_lineage
    assert (
        first_bundle.computed_context_lineage_sha256
        == second_bundle.computed_context_lineage_sha256
    )
    assert first_bundle.computed_context_lineage == second_bundle.computed_context_lineage
    assert len(first_bundle.policy_lineage_sha256) == 64
    assert len(first_bundle.computed_context_lineage_sha256) == 64
    assert sum(int(item["decision_count"]) for item in first_bundle.policy_lineage) == 2
    assert (
        sum(int(item["decision_count"]) for item in first_bundle.computed_context_lineage)
        == 2
    )
    assert all(
        int(item["decision_count"]) >= 1
        and len(str(item["policy_document_sha256"])) == 64
        and str(item["policy_document_schema_version"]).strip()
        for item in first_bundle.policy_lineage
    )
    assert all(
        int(item["decision_count"]) >= 1
        and str(item["month_start"]).strip()
        and str(item["month_end"]).strip()
        and str(item["data_source_mode"]).strip()
        for item in first_bundle.computed_context_lineage
    )
    decision_rows = list(csv.DictReader(io.StringIO(first_bundle.decisions_csv)))
    assert len(decision_rows) == 2
    assert all(
        row["policy_document_schema_version"] == "valdrix.enforcement.policy.v1"
        and len(row["policy_document_sha256"]) == 64
        for row in decision_rows
    )
    assert all(
        row["computed_context_month_start"]
        and row["computed_context_month_end"]
        and row["computed_context_data_source_mode"]
        for row in decision_rows
    )

    first_manifest = service.build_signed_export_manifest(
        tenant_id=tenant.id,
        bundle=first_bundle,
    )
    second_manifest = service.build_signed_export_manifest(
        tenant_id=tenant.id,
        bundle=second_bundle,
    )
    assert first_manifest.content_sha256 == second_manifest.content_sha256
    assert first_manifest.signature == second_manifest.signature
    assert first_manifest.signature_algorithm == "hmac-sha256"
    assert first_manifest.policy_lineage_sha256 == first_bundle.policy_lineage_sha256
    assert first_manifest.policy_lineage == first_bundle.policy_lineage
    assert (
        first_manifest.computed_context_lineage_sha256
        == first_bundle.computed_context_lineage_sha256
    )
    assert first_manifest.computed_context_lineage == first_bundle.computed_context_lineage
    assert first_manifest.signature_key_id == second_manifest.signature_key_id
    assert first_manifest.to_payload()["manifest_content_sha256"] == first_manifest.content_sha256

    decision_reader = csv.reader(io.StringIO(first_bundle.decisions_csv))
    approval_reader = csv.reader(io.StringIO(first_bundle.approvals_csv))
    decision_rows = list(decision_reader)
    approval_rows = list(approval_reader)
    assert len(decision_rows) == first_bundle.decision_count_exported + 1
    assert len(approval_rows) == first_bundle.approval_count_exported + 1


@pytest.mark.asyncio
async def test_export_policy_lineage_remains_consistent_across_policy_updates(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    first_policy = await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.SOFT,
        terraform_mode_nonprod=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        plan_monthly_ceiling_usd=Decimal("1000"),
        enterprise_monthly_ceiling_usd=Decimal("2000"),
        auto_approve_below_monthly_usd=Decimal("25"),
        hard_deny_above_monthly_usd=Decimal("5000"),
        default_ttl_seconds=900,
    )

    first_hash = first_policy.policy_document_sha256
    first_version = int(first_policy.policy_version)
    assert len(first_hash) == 64

    first_decision = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.policy-hash-1",
            estimated_monthly_delta_usd=Decimal("30"),
            estimated_hourly_delta_usd=Decimal("0.04"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="policy-lineage-1",
        ),
    )

    assert first_decision.decision.policy_document_sha256 == first_hash
    assert int(first_decision.decision.policy_version) == first_version

    second_policy = await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.SOFT,
        terraform_mode_nonprod=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        plan_monthly_ceiling_usd=Decimal("1"),
        enterprise_monthly_ceiling_usd=Decimal("2"),
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("10"),
        default_ttl_seconds=300,
        policy_document={
            "schema_version": POLICY_DOCUMENT_SCHEMA_VERSION,
            "mode_matrix": {
                "terraform_default": "hard",
                "terraform_prod": "hard",
                "terraform_nonprod": "shadow",
                "k8s_admission_default": "shadow",
                "k8s_admission_prod": "hard",
                "k8s_admission_nonprod": "soft",
            },
            "approval": {
                "require_approval_prod": True,
                "require_approval_nonprod": True,
                "enforce_prod_requester_reviewer_separation": True,
                "enforce_nonprod_requester_reviewer_separation": False,
                "routing_rules": [],
            },
            "entitlements": {
                "plan_monthly_ceiling_usd": "333.3",
                "enterprise_monthly_ceiling_usd": "444.4",
                "auto_approve_below_monthly_usd": "5",
                "hard_deny_above_monthly_usd": "900",
            },
            "execution": {"default_ttl_seconds": 1800},
        },
    )

    second_hash = second_policy.policy_document_sha256
    second_version = int(second_policy.policy_version)
    assert second_hash != first_hash
    assert second_version > first_version
    # Policy document remains the single source of truth even when scalar
    # arguments are provided in the same update call.
    assert second_policy.terraform_mode == EnforcementMode.HARD
    assert second_policy.k8s_admission_mode == EnforcementMode.SHADOW
    assert second_policy.plan_monthly_ceiling_usd == Decimal("333.3000")

    second_decision = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.policy-hash-2",
            estimated_monthly_delta_usd=Decimal("20"),
            estimated_hourly_delta_usd=Decimal("0.03"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="policy-lineage-2",
        ),
    )

    assert second_decision.decision.policy_document_sha256 == second_hash
    assert int(second_decision.decision.policy_version) == second_version

    now = datetime.now(timezone.utc)
    bundle = await service.build_export_bundle(
        tenant_id=tenant.id,
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=1),
        max_rows=1000,
    )

    decision_rows = list(csv.DictReader(io.StringIO(bundle.decisions_csv)))
    row_by_id = {str(row["decision_id"]): row for row in decision_rows}
    assert row_by_id[str(first_decision.decision.id)]["policy_document_sha256"] == first_hash
    assert row_by_id[str(second_decision.decision.id)]["policy_document_sha256"] == second_hash
    assert int(row_by_id[str(first_decision.decision.id)]["policy_version"]) == first_version
    assert int(row_by_id[str(second_decision.decision.id)]["policy_version"]) == second_version

    lineage_counts = {
        str(item["policy_document_sha256"]): int(item["decision_count"])
        for item in bundle.policy_lineage
    }
    assert lineage_counts[first_hash] == 1
    assert lineage_counts[second_hash] == 1
    assert sum(lineage_counts.values()) == 2
    assert len(bundle.computed_context_lineage_sha256) == 64
    assert sum(
        int(item["decision_count"]) for item in bundle.computed_context_lineage
    ) == 2


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
async def test_build_export_bundle_rejects_max_rows_upper_bound_and_invalid_window(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    now = datetime.now(timezone.utc)

    with pytest.raises(HTTPException) as max_rows_exc:
        await service.build_export_bundle(
            tenant_id=tenant.id,
            window_start=now - timedelta(days=1),
            window_end=now + timedelta(days=1),
            max_rows=50001,
        )
    assert max_rows_exc.value.status_code == 422
    assert "max_rows must be <=" in str(max_rows_exc.value.detail)

    with pytest.raises(HTTPException) as window_exc:
        await service.build_export_bundle(
            tenant_id=tenant.id,
            window_start=now,
            window_end=now,
            max_rows=1000,
        )
    assert window_exc.value.status_code == 422
    assert "window_start must be before window_end" in str(window_exc.value.detail)


@pytest.mark.asyncio
async def test_build_export_bundle_rejects_when_decision_count_exceeds_max_rows(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()

    first_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="export-bundle-count-limit-1",
    )
    second_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="export-bundle-count-limit-2",
    )
    assert first_gate.approval is not None
    assert second_gate.approval is not None

    counter = _FakeCounter()
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_EXPORT_EVENTS_TOTAL",
        counter,
    )

    now = datetime.now(timezone.utc)
    service = EnforcementService(db)
    with pytest.raises(HTTPException) as exc:
        await service.build_export_bundle(
            tenant_id=tenant.id,
            window_start=now - timedelta(days=1),
            window_end=now + timedelta(days=1),
            max_rows=1,
        )

    assert exc.value.status_code == 422
    assert "exceeds max_rows" in str(exc.value.detail)
    assert ("artifact", "bundle") in tuple(counter.calls[0][0].items())
    assert counter.calls[0][0]["artifact"] == "bundle"
    assert counter.calls[0][0]["outcome"] == "rejected_limit"


@pytest.mark.asyncio
async def test_build_export_bundle_empty_window_returns_empty_lineage_and_success_metric(
    db, monkeypatch
) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    counter = _FakeCounter()
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_EXPORT_EVENTS_TOTAL",
        counter,
    )

    now = datetime.now(timezone.utc)
    bundle = await service.build_export_bundle(
        tenant_id=tenant.id,
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=1),
        max_rows=1000,
    )

    assert bundle.decision_count_db == 0
    assert bundle.decision_count_exported == 0
    assert bundle.approval_count_db == 0
    assert bundle.approval_count_exported == 0
    assert bundle.policy_lineage == []
    assert bundle.computed_context_lineage == []
    assert bundle.parity_ok is True
    assert len(bundle.policy_lineage_sha256) == 64
    assert len(bundle.computed_context_lineage_sha256) == 64
    assert counter.calls[-1][0]["artifact"] == "bundle"
    assert counter.calls[-1][0]["outcome"] == "success"


@pytest.mark.asyncio
async def test_build_signed_export_manifest_requires_signing_secret(db, monkeypatch) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()

    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="export-signing-key-required-1",
    )
    assert gate.approval is not None

    now = datetime.now(timezone.utc)
    service = EnforcementService(db)
    bundle = await service.build_export_bundle(
        tenant_id=tenant.id,
        window_start=now - timedelta(days=1),
        window_end=now + timedelta(days=1),
        max_rows=1000,
    )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_SIGNING_SECRET="",
            SUPABASE_JWT_SECRET="",
            ENFORCEMENT_EXPORT_SIGNING_KID="export-key-v1",
            JWT_SIGNING_KID="",
        ),
    )

    with pytest.raises(HTTPException) as exc:
        service.build_signed_export_manifest(
            tenant_id=tenant.id,
            bundle=bundle,
        )

    assert exc.value.status_code == 503
    assert "signing key" in str(exc.value.detail).lower()


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
    assert entry.burn_rate_daily_usd is not None
    assert entry.forecast_eom_usd is not None
    assert entry.risk_class in {"low", "medium", "high"}
    assert entry.anomaly_signal in {True, False}
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
async def test_ledger_captures_approval_linkage_and_status_transitions(db) -> None:
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
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )

    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.web",
            estimated_monthly_delta_usd=Decimal("80"),
            estimated_hourly_delta_usd=Decimal("0.10"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="ledger-approval-linkage-1",
        ),
    )
    assert gate.approval is not None
    assert gate.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL

    pending_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(pending_rows) == 1
    assert pending_rows[0].approval_request_id == gate.approval.id
    assert pending_rows[0].approval_status == EnforcementApprovalStatus.PENDING

    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    approval, _, _, _ = await service.approve_request(
        tenant_id=tenant.id,
        approval_id=gate.approval.id,
        reviewer=reviewer,
        notes="approve for ledger linkage",
    )
    assert approval.status == EnforcementApprovalStatus.APPROVED

    rows_after_approve = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(rows_after_approve) == 2
    assert rows_after_approve[-1].approval_request_id == gate.approval.id
    assert rows_after_approve[-1].approval_status == EnforcementApprovalStatus.APPROVED


@pytest.mark.asyncio
async def test_create_approval_request_appends_ledger_linkage_for_existing_decision(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("0"),
        hard_deny_above_monthly_usd=Decimal("2500"),
        default_ttl_seconds=900,
    )
    await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )

    gate = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.db.aws_db_instance.main",
            estimated_monthly_delta_usd=Decimal("100"),
            estimated_hourly_delta_usd=Decimal("0.14"),
            metadata={"resource_type": "aws_db_instance"},
            idempotency_key="ledger-create-approval-linkage-1",
            dry_run=True,
        ),
    )
    assert gate.decision.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert gate.approval is None

    initial_rows = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(initial_rows) == 1
    assert initial_rows[0].approval_request_id is None
    assert initial_rows[0].approval_status is None

    created = await service.create_or_get_approval_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=gate.decision.id,
        notes="create approval linkage snapshot",
    )
    assert created.status == EnforcementApprovalStatus.PENDING

    rows_after_create = (
        await db.execute(
            select(EnforcementDecisionLedger)
            .where(EnforcementDecisionLedger.decision_id == gate.decision.id)
            .order_by(
                EnforcementDecisionLedger.recorded_at.asc(),
                EnforcementDecisionLedger.id.asc(),
            )
        )
    ).scalars().all()
    assert len(rows_after_create) == 2
    assert rows_after_create[-1].approval_request_id == created.id
    assert rows_after_create[-1].approval_status == EnforcementApprovalStatus.PENDING


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


@pytest.mark.asyncio
async def test_budget_and_credit_list_and_validation_branches(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    assert await service.list_budgets(tenant.id) == []
    with pytest.raises(HTTPException, match="monthly_limit_usd must be >= 0"):
        await service.upsert_budget(
            tenant_id=tenant.id,
            actor_id=actor_id,
            scope_key="default",
            monthly_limit_usd=Decimal("-1"),
            active=True,
        )

    budget = await service.upsert_budget(
        tenant_id=tenant.id,
        actor_id=actor_id,
        scope_key="default",
        monthly_limit_usd=Decimal("1000"),
        active=True,
    )
    budgets = await service.list_budgets(tenant.id)
    assert [item.id for item in budgets] == [budget.id]

    assert await service.list_credits(tenant.id) == []
    with pytest.raises(HTTPException, match="total_amount_usd must be > 0"):
        await service.create_credit_grant(
            tenant_id=tenant.id,
            actor_id=actor_id,
            scope_key="default",
            total_amount_usd=Decimal("0"),
            expires_at=None,
            reason="invalid",
        )


@pytest.mark.asyncio
async def test_create_or_get_approval_request_branch_paths(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    actor_id = uuid4()

    with pytest.raises(HTTPException, match="Decision not found"):
        await service.create_or_get_approval_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=uuid4(),
            notes="missing",
        )

    await service.update_policy(
        tenant_id=tenant.id,
        terraform_mode=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        require_approval_for_prod=False,
        require_approval_for_nonprod=False,
        auto_approve_below_monthly_usd=Decimal("100"),
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
    gate_without_approval = await service.evaluate_gate(
        tenant_id=tenant.id,
        actor_id=actor_id,
        source=EnforcementSource.TERRAFORM,
        gate_input=GateInput(
            project_id="default",
            environment="nonprod",
            action="terraform.apply",
            resource_reference="module.app.aws_instance.no-approval",
            estimated_monthly_delta_usd=Decimal("20"),
            estimated_hourly_delta_usd=Decimal("0.03"),
            metadata={"resource_type": "aws_instance"},
            idempotency_key="approval-create-branch-no-approval",
        ),
    )
    assert gate_without_approval.decision.decision == EnforcementDecisionType.ALLOW

    with pytest.raises(HTTPException, match="can only be created"):
        await service.create_or_get_approval_request(
            tenant_id=tenant.id,
            actor_id=actor_id,
            decision_id=gate_without_approval.decision.id,
            notes="not allowed",
        )

    pending_gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="approval-create-branch-existing",
    )
    existing = await service.create_or_get_approval_request(
        tenant_id=tenant.id,
        actor_id=actor_id,
        decision_id=pending_gate.decision.id,
        notes="reuse",
    )
    assert existing.id == pending_gate.approval.id


@pytest.mark.asyncio
async def test_list_pending_approvals_reviewer_filtering_branch_paths(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="approval-list-branch-1",
    )
    service = EnforcementService(db)

    pending = await service.list_pending_approvals(
        tenant_id=tenant.id,
        reviewer=None,
        limit=50,
    )
    assert len(pending) == 1
    assert pending[0][0].id == gate.approval.id

    reviewer = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )

    async def _reject_authority(**_kwargs):
        raise HTTPException(status_code=403, detail="forbidden")

    service._enforce_reviewer_authority = _reject_authority  # type: ignore[method-assign]
    filtered = await service.list_pending_approvals(
        tenant_id=tenant.id,
        reviewer=reviewer,
        limit=50,
    )
    assert filtered == []


@pytest.mark.asyncio
async def test_list_pending_approvals_reviewer_filtering_includes_authorized_rows(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="nonprod",
        require_approval_for_prod=False,
        require_approval_for_nonprod=True,
        idempotency_key="approval-list-branch-allow-1",
    )
    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    authority_calls: list[tuple[str, str]] = []

    async def _allow_authority(*, approval, decision, **_kwargs):
        authority_calls.append((str(approval.id), str(decision.id)))
        return {"required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD}

    service._enforce_reviewer_authority = _allow_authority  # type: ignore[method-assign]
    filtered = await service.list_pending_approvals(
        tenant_id=tenant.id,
        reviewer=reviewer,
        limit=50,
    )

    assert len(filtered) == 1
    assert filtered[0][0].id == gate.approval.id
    assert filtered[0][1].id == gate.decision.id
    assert authority_calls == [(str(gate.approval.id), str(gate.decision.id))]


@pytest.mark.asyncio
async def test_approve_request_marks_expired_approval_branch(db) -> None:
    tenant = await _seed_tenant(db)
    actor_id = uuid4()
    gate = await _issue_pending_approval(
        db=db,
        tenant_id=tenant.id,
        actor_id=actor_id,
        environment="prod",
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        idempotency_key="approve-expired-branch-1",
    )
    assert gate.approval is not None
    gate.approval.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(gate.approval)
    await db.commit()

    service = EnforcementService(db)
    reviewer = CurrentUser(
        id=uuid4(),
        email="owner@example.com",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    with pytest.raises(HTTPException, match="has expired"):
        await service.approve_request(
            tenant_id=tenant.id,
            approval_id=gate.approval.id,
            reviewer=reviewer,
            notes="too late",
        )

    await db.refresh(gate.approval)
    await db.refresh(gate.decision)
    assert gate.approval.status == EnforcementApprovalStatus.EXPIRED
    assert gate.decision.reservation_active is False
    response_payload = gate.decision.response_payload or {}
    assert "approval_expired_at" in response_payload
