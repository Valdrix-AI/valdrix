from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.modules.enforcement.domain.service as enforcement_service_module
from app.models.enforcement import (
    EnforcementApprovalStatus,
    EnforcementCreditPoolType,
    EnforcementDecisionType,
    EnforcementMode,
    EnforcementPolicy,
    EnforcementSource,
)
from app.models.tenant import Tenant
from app.modules.enforcement.domain.service import (
    EnforcementService,
    GateEvaluationResult,
    gate_result_to_response,
)
from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
)


def _service() -> EnforcementService:
    return EnforcementService(db=SimpleNamespace())


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeCounter":
        self._labels = dict(labels)
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append((dict(self._labels), float(amount)))


class _FakeHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeHistogram":
        self._labels = dict(labels)
        return self

    def observe(self, amount: float) -> None:
        self.calls.append((dict(self._labels), float(amount)))


async def _seed_tenant(db) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="enforcement-helper-tenant",
        plan="pro",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


def _base_policy_update_kwargs(*, tenant_id) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "terraform_mode": EnforcementMode.SOFT,
        "k8s_admission_mode": EnforcementMode.SOFT,
        "require_approval_for_prod": True,
        "require_approval_for_nonprod": False,
        "auto_approve_below_monthly_usd": Decimal("10"),
        "hard_deny_above_monthly_usd": Decimal("100"),
        "default_ttl_seconds": 900,
    }


def test_datetime_and_numeric_helpers_cover_edge_cases() -> None:
    now = enforcement_service_module._utcnow()
    assert now.tzinfo is timezone.utc

    naive = datetime(2026, 2, 1, 12, 0, 0)
    aware = datetime(2026, 2, 1, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))

    assert enforcement_service_module._as_utc(naive).tzinfo is timezone.utc
    assert enforcement_service_module._as_utc(aware).hour == 12

    assert enforcement_service_module._parse_iso_datetime(aware) == enforcement_service_module._as_utc(aware)
    assert enforcement_service_module._parse_iso_datetime("2026-02-01T12:00:00Z") == datetime(
        2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc
    )
    assert enforcement_service_module._parse_iso_datetime("invalid") is None
    assert enforcement_service_module._parse_iso_datetime(1234) is None

    assert enforcement_service_module._iso_or_empty(None) == ""
    assert enforcement_service_module._iso_or_empty(naive).endswith("+00:00")

    assert enforcement_service_module._to_decimal(Decimal("1.23")) == Decimal("1.23")
    assert enforcement_service_module._to_decimal("2.5") == Decimal("2.5")
    assert enforcement_service_module._to_decimal(None, default=Decimal("7")) == Decimal("7")
    assert enforcement_service_module._to_decimal("not-a-number", default=Decimal("9")) == Decimal("9")

    assert enforcement_service_module._quantize(Decimal("1.23456"), "0.0001") == Decimal("1.2346")


def test_string_hash_and_json_helpers_cover_edge_cases() -> None:
    assert enforcement_service_module._normalize_environment("production") == "prod"
    assert enforcement_service_module._normalize_environment("staging") == "nonprod"
    assert enforcement_service_module._normalize_environment(" ") == "nonprod"
    assert enforcement_service_module._is_production_environment("live") is True
    assert enforcement_service_module._is_production_environment("dev") is False

    normalized = enforcement_service_module._normalize_string_list(
        [" Prod ", "prod", "stage", "  "],
        normalizer=enforcement_service_module._normalize_environment,
    )
    assert normalized == ["prod", "nonprod"]

    assert enforcement_service_module._normalize_allowed_reviewer_roles(None) == [
        "owner",
        "admin",
    ]
    assert enforcement_service_module._normalize_allowed_reviewer_roles(
        ["owner", "OWNER", "member", "invalid"]
    ) == ["owner", "member"]
    assert enforcement_service_module._normalize_allowed_reviewer_roles(["invalid"]) == [
        "owner",
        "admin",
    ]

    assert (
        enforcement_service_module._default_required_permission_for_environment("prod")
        == APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )
    assert (
        enforcement_service_module._default_required_permission_for_environment("dev")
        == APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
    )

    payload_a = {"b": Decimal("1.20"), "a": datetime(2026, 2, 1, tzinfo=timezone.utc)}
    payload_b = {"a": datetime(2026, 2, 1, tzinfo=timezone.utc), "b": Decimal("1.20")}
    assert enforcement_service_module._payload_sha256(payload_a) == enforcement_service_module._payload_sha256(payload_b)

    assert enforcement_service_module._sanitize_csv_cell(None) == ""
    assert enforcement_service_module._sanitize_csv_cell("=SUM(1,2)") == "'=SUM(1,2)"
    assert enforcement_service_module._sanitize_csv_cell("-100") == "'-100"
    assert enforcement_service_module._sanitize_csv_cell("line1\nline2") == "line1 line2"

    unique = enforcement_service_module._unique_reason_codes([
        " budget_exceeded ",
        "BUDGET_EXCEEDED",
        "",
        "shadow_mode_budget_override",
    ])
    assert unique == ["budget_exceeded", "shadow_mode_budget_override"]

    assert enforcement_service_module._json_default(Decimal("1.23")) == "1.23"
    now = datetime.now(timezone.utc)
    assert enforcement_service_module._json_default(now) == now.isoformat()
    with pytest.raises(TypeError):
        enforcement_service_module._json_default(object())


def test_computed_context_snapshot_int_parsing_edge_cases() -> None:
    snapshot = enforcement_service_module._computed_context_snapshot(
        {
            "computed_context": {
                "context_version": " v1 ",
                "generated_at": "2026-02-26T00:00:00Z",
                "month_start": "2026-02-01",
                "month_end": "2026-02-29",
                "month_elapsed_days": None,  # line 480 path
                "month_total_days": True,  # line 482 path
                "observed_cost_days": object(),  # line 484 path
                "latest_cost_date": "2026-02-25",
                "data_source_mode": "actual",
            }
        }
    )
    assert snapshot["month_elapsed_days"] == 0
    assert snapshot["month_total_days"] == 1
    assert snapshot["observed_cost_days"] == 0
    assert snapshot["context_version"] == "v1"

    invalid_numeric = enforcement_service_module._computed_context_snapshot(
        {
            "computed_context": {
                "month_elapsed_days": "not-an-int",  # line 487/488 path
                "month_total_days": Decimal("30"),
                "observed_cost_days": 12.9,
            }
        }
    )
    assert invalid_numeric["month_elapsed_days"] == 0
    assert invalid_numeric["month_total_days"] == 30
    assert invalid_numeric["observed_cost_days"] == 12

    non_mapping = enforcement_service_module._computed_context_snapshot(
        {"computed_context": ["unexpected"]}
    )
    assert non_mapping["month_elapsed_days"] == 0
    assert non_mapping["month_total_days"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "detail_substring"),
    [
        ({"hard_deny_above_monthly_usd": Decimal("0")}, "greater than 0"),
        ({"auto_approve_below_monthly_usd": Decimal("-1")}, "greater than or equal to 0"),
        (
            {
                "auto_approve_below_monthly_usd": Decimal("101"),
                "hard_deny_above_monthly_usd": Decimal("100"),
            },
            "cannot exceed",
        ),
        (
            {"plan_monthly_ceiling_usd": Decimal("-1")},
            "greater than or equal to 0",
        ),
        (
            {"enterprise_monthly_ceiling_usd": Decimal("-1")},
            "greater than or equal to 0",
        ),
    ],
)
async def test_update_policy_rejects_invalid_thresholds(db, overrides, detail_substring: str) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)
    kwargs = _base_policy_update_kwargs(tenant_id=tenant.id)
    kwargs.update(overrides)

    with pytest.raises((HTTPException, ValidationError)) as exc:
        await service.update_policy(**kwargs)

    if isinstance(exc.value, HTTPException):
        assert exc.value.status_code == 422
        rendered = str(exc.value.detail)
    else:
        rendered = str(exc.value)
    assert detail_substring in rendered


@pytest.mark.asyncio
async def test_update_policy_normalizes_values_and_increments_version(db) -> None:
    tenant = await _seed_tenant(db)
    service = EnforcementService(db)

    kwargs = _base_policy_update_kwargs(tenant_id=tenant.id)
    kwargs.update(
        {
            "terraform_mode": EnforcementMode.HARD,
            "terraform_mode_prod": None,
            "terraform_mode_nonprod": EnforcementMode.SHADOW,
            "k8s_admission_mode": EnforcementMode.SOFT,
            "k8s_admission_mode_prod": None,
            "k8s_admission_mode_nonprod": EnforcementMode.HARD,
            "default_ttl_seconds": 999999,
            "approval_routing_rules": [
                {
                    "rule_id": "finance-prod",
                    "environments": ["production", "Prod"],
                    "action_prefixes": ["terraform.", "terraform."],
                    "min_monthly_delta_usd": "10",
                    "max_monthly_delta_usd": "250",
                    "risk_levels": ["HIGH", "high"],
                    "allowed_reviewer_roles": ["owner", "member", "owner"],
                    "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                    "require_requester_reviewer_separation": True,
                }
            ],
        }
    )
    policy = await service.update_policy(**kwargs)

    assert policy.terraform_mode == EnforcementMode.HARD
    assert policy.terraform_mode_prod == EnforcementMode.HARD
    assert policy.terraform_mode_nonprod == EnforcementMode.SHADOW
    assert policy.k8s_admission_mode_nonprod == EnforcementMode.HARD
    assert policy.default_ttl_seconds == 86400
    assert policy.policy_version == 2

    rules = policy.approval_routing_rules
    assert isinstance(rules, list)
    assert rules[0]["environments"] == ["prod"]
    assert rules[0]["action_prefixes"] == ["terraform."]
    assert rules[0]["risk_levels"] == ["high"]
    assert rules[0]["allowed_reviewer_roles"] == ["owner", "member"]


def test_normalize_policy_approval_routing_rules_rejects_invalid_inputs() -> None:
    service = _service()

    with pytest.raises(HTTPException, match="cannot exceed 64 rules"):
        service._normalize_policy_approval_routing_rules([{"rule_id": f"r{i}"} for i in range(65)])

    invalid_cases = [
        (["not-object"], "must be an object"),
        ([{}], "rule_id is required"),
        ([{"rule_id": "x" * 65}], "exceeds 64 chars"),
        ([{"rule_id": "dup"}, {"rule_id": "DUP"}], "Duplicate approval routing"),
        ([{"rule_id": "r1", "min_monthly_delta_usd": "-1"}], "min_monthly_delta_usd must be >= 0"),
        ([{"rule_id": "r1", "max_monthly_delta_usd": "-1"}], "max_monthly_delta_usd must be >= 0"),
        (
            [
                {
                    "rule_id": "r1",
                    "min_monthly_delta_usd": "10",
                    "max_monthly_delta_usd": "5",
                }
            ],
            "cannot exceed max_monthly_delta_usd",
        ),
        (
            [{"rule_id": "r1", "required_permission": "invalid"}],
            "required_permission must be one of",
        ),
        (
            [{"rule_id": "r1", "require_requester_reviewer_separation": "yes"}],
            "must be a boolean",
        ),
    ]

    for rules, expected in invalid_cases:
        with pytest.raises(HTTPException) as exc:
            service._normalize_policy_approval_routing_rules(rules)
        assert expected in str(exc.value.detail)


def test_resolve_policy_mode_covers_source_and_environment_paths() -> None:
    service = _service()
    tenant_id = uuid4()
    policy = EnforcementPolicy(
        tenant_id=tenant_id,
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.SHADOW,
        k8s_admission_mode=EnforcementMode.SHADOW,
        k8s_admission_mode_prod=EnforcementMode.SOFT,
        k8s_admission_mode_nonprod=EnforcementMode.HARD,
    )

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.TERRAFORM,
        environment="prod",
    )
    assert (mode, trace) == (EnforcementMode.HARD, "terraform:prod")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.TERRAFORM,
        environment="staging",
    )
    assert (mode, trace) == (EnforcementMode.SHADOW, "terraform:nonprod")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.TERRAFORM,
        environment="custom",
    )
    assert (mode, trace) == (EnforcementMode.SOFT, "terraform:default")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.K8S_ADMISSION,
        environment="prod",
    )
    assert (mode, trace) == (EnforcementMode.SOFT, "k8s_admission:prod")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.K8S_ADMISSION,
        environment="dev",
    )
    assert (mode, trace) == (EnforcementMode.HARD, "k8s_admission:nonprod")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.K8S_ADMISSION,
        environment="qa-custom",
    )
    assert (mode, trace) == (EnforcementMode.SHADOW, "k8s_admission:default")

    mode, trace = service._resolve_policy_mode(
        policy=policy,
        source=EnforcementSource.CLOUD_EVENT,
        environment="prod",
    )
    assert (mode, trace) == (EnforcementMode.SHADOW, "fallback:k8s_admission_default")


def test_materialize_policy_contract_rejects_invalid_policy_document_and_threshold_edges() -> None:
    service = _service()

    def _kwargs() -> dict[str, object]:
        return {
            "terraform_mode": EnforcementMode.SOFT,
            "terraform_mode_prod": None,
            "terraform_mode_nonprod": None,
            "k8s_admission_mode": EnforcementMode.SOFT,
            "k8s_admission_mode_prod": None,
            "k8s_admission_mode_nonprod": None,
            "require_approval_for_prod": False,
            "require_approval_for_nonprod": False,
            "plan_monthly_ceiling_usd": None,
            "enterprise_monthly_ceiling_usd": None,
            "auto_approve_below_monthly_usd": Decimal("10"),
            "hard_deny_above_monthly_usd": Decimal("100"),
            "default_ttl_seconds": 900,
            "enforce_prod_requester_reviewer_separation": True,
            "enforce_nonprod_requester_reviewer_separation": False,
            "approval_routing_rules": [],
            "policy_document": None,
        }

    with pytest.raises(HTTPException) as invalid_doc_exc:
        service._materialize_policy_contract(
            **{
                **_kwargs(),
                "policy_document": {"schema_version": "invalid-only"},
            }
        )
    assert invalid_doc_exc.value.status_code == 422
    assert invalid_doc_exc.value.detail["message"] == "policy_document is invalid"
    assert invalid_doc_exc.value.detail["errors"]

    # Sub-quantum positive hard deny passes pydantic `gt=0` but quantizes to 0.0000,
    # exercising the helper's post-quantization safety check (service.py line 812).
    with pytest.raises(HTTPException) as hard_deny_exc:
        service._materialize_policy_contract(
            **{
                **_kwargs(),
                "hard_deny_above_monthly_usd": Decimal("0.00004"),
            }
        )
    assert hard_deny_exc.value.status_code == 422
    assert "hard_deny_above_monthly_usd must be greater than 0" in str(
        hard_deny_exc.value.detail
    )

    # These negative values are rejected earlier by PolicyDocumentEntitlementMatrix
    # field constraints (pydantic), so the helper's redundant defensive checks do
    # not execute in the normal code path.
    prevalidated_cases = [
        {"auto_approve_below_monthly_usd": Decimal("-0.0001")},
        {"plan_monthly_ceiling_usd": Decimal("-1")},
        {"enterprise_monthly_ceiling_usd": Decimal("-1")},
    ]
    for overrides in prevalidated_cases:
        with pytest.raises(ValidationError):
            service._materialize_policy_contract(**{**_kwargs(), **overrides})


def test_policy_entitlement_matrix_prevalidates_negative_thresholds() -> None:
    # service.py defensive guards at lines 817/844/849 should remain unreachable
    # in normal flow because entitlement model validation fails earlier.
    with pytest.raises(ValidationError):
        enforcement_service_module.PolicyDocumentEntitlementMatrix(
            auto_approve_below_monthly_usd=Decimal("-0.0001"),
            hard_deny_above_monthly_usd=Decimal("1"),
        )

    with pytest.raises(ValidationError):
        enforcement_service_module.PolicyDocumentEntitlementMatrix(
            plan_monthly_ceiling_usd=Decimal("-1"),
            hard_deny_above_monthly_usd=Decimal("1"),
        )

    with pytest.raises(ValidationError):
        enforcement_service_module.PolicyDocumentEntitlementMatrix(
            enterprise_monthly_ceiling_usd=Decimal("-1"),
            hard_deny_above_monthly_usd=Decimal("1"),
        )


def test_reserve_amount_quantization_invariant_proves_defensive_guard() -> None:
    # In _reserve_credit_from_grants(), once both guards pass:
    #  - remaining > 0 (already quantized to 4dp)
    #  - grant_remaining > 0 (already quantized to 4dp)
    # then reserve_amount = quantize(min(...), 4dp) must be > 0. The line-4210
    # guard is therefore defensive against arithmetic/coercion regressions.
    step = Decimal("0.0001")
    values = [step * Decimal(i) for i in range(1, 51)]  # 0.0001 .. 0.0050
    for remaining in values:
        for grant_remaining in values:
            reserve_amount = enforcement_service_module._quantize(
                min(remaining, grant_remaining),
                "0.0001",
            )
            assert reserve_amount > Decimal("0.0000")


@pytest.mark.asyncio
async def test_resolve_monthly_ceiling_prefers_policy_then_tier_limits(monkeypatch) -> None:
    service = _service()
    tenant_id = uuid4()
    policy_with_configured_plan = EnforcementPolicy(
        tenant_id=tenant_id,
        plan_monthly_ceiling_usd=Decimal("500.12999"),
        enterprise_monthly_ceiling_usd=None,
    )

    plan = await service._resolve_plan_monthly_ceiling_usd(
        policy=policy_with_configured_plan,
        tenant_tier=enforcement_service_module.PricingTier.PRO,
    )
    assert plan == Decimal("500.1300")

    monkeypatch.setattr(
        enforcement_service_module,
        "get_tier_limit",
        lambda _tier, key: Decimal("1200.5555") if key.endswith("enterprise_monthly_ceiling_usd") else Decimal("0"),
    )

    plan_from_limit = await service._resolve_plan_monthly_ceiling_usd(
        policy=EnforcementPolicy(tenant_id=tenant_id, plan_monthly_ceiling_usd=None),
        tenant_tier=enforcement_service_module.PricingTier.PRO,
    )
    assert plan_from_limit is None

    enterprise = await service._resolve_enterprise_monthly_ceiling_usd(
        policy=policy_with_configured_plan,
        tenant_tier=enforcement_service_module.PricingTier.PRO,
    )
    assert enterprise == Decimal("1200.5555")


def test_derive_risk_assessment_covers_high_medium_and_low_scores() -> None:
    service = _service()

    high_gate = enforcement_service_module.GateInput(
        project_id="p1",
        environment="prod",
        action="terraform.destroy",
        resource_reference="cluster/main-postgres",
        estimated_monthly_delta_usd=Decimal("7500"),
        estimated_hourly_delta_usd=Decimal("10"),
        metadata={"criticality": "critical", "resource_type": "database"},
    )
    high_class, high_score, high_factors = service._derive_risk_assessment(
        gate_input=high_gate,
        is_production=True,
        anomaly_signal=True,
    )
    assert high_class == "high"
    assert high_score >= 8
    assert "destructive_action" in high_factors
    assert "anomaly_spike_signal" in high_factors

    medium_gate = enforcement_service_module.GateInput(
        project_id="p2",
        environment="staging",
        action="terraform.apply",
        resource_reference="service/api",
        estimated_monthly_delta_usd=Decimal("1200"),
        estimated_hourly_delta_usd=Decimal("1"),
        metadata={"criticality": "medium", "resource_type": "database"},
    )
    medium_class, _, medium_factors = service._derive_risk_assessment(
        gate_input=medium_gate,
        is_production=False,
        anomaly_signal=False,
    )
    assert medium_class == "medium"
    assert "moderate_monthly_delta" in medium_factors

    low_gate = enforcement_service_module.GateInput(
        project_id="p3",
        environment="dev",
        action="terraform.plan",
        resource_reference="misc/worker",
        estimated_monthly_delta_usd=Decimal("10"),
        estimated_hourly_delta_usd=Decimal("0.1"),
        metadata={"resource_type": "app"},
    )
    low_class, low_score, low_factors = service._derive_risk_assessment(
        gate_input=low_gate,
        is_production=False,
        anomaly_signal=False,
    )
    assert low_class == "low"
    assert low_score == 0
    assert low_factors == tuple()


def test_resolve_approval_routing_trace_matches_policy_rules() -> None:
    service = _service()
    tenant_id = uuid4()
    policy = EnforcementPolicy(
        tenant_id=tenant_id,
        enforce_prod_requester_reviewer_separation=True,
        approval_routing_rules=[
            {
                "rule_id": "team-prod-high",
                "enabled": True,
                "environments": ["prod"],
                "action_prefixes": ["terraform.apply"],
                "min_monthly_delta_usd": "100",
                "max_monthly_delta_usd": "1000",
                "risk_levels": ["critical"],
                "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                "allowed_reviewer_roles": ["owner", "member"],
                "require_requester_reviewer_separation": True,
            }
        ],
    )

    decision = SimpleNamespace(
        environment="production",
        action="terraform.apply.module",
        estimated_monthly_delta_usd=Decimal("500"),
        request_payload={"metadata": {"risk_level": "critical"}},
    )

    trace = service._resolve_approval_routing_trace(policy=policy, decision=decision)
    assert trace["matched_rule"] == "policy_rule"
    assert trace["rule_id"] == "team-prod-high"
    assert trace["required_permission"] == APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    assert trace["allowed_reviewer_roles"] == ["owner", "member"]

    unmatched_decision = SimpleNamespace(
        environment="dev",
        action="terraform.plan",
        estimated_monthly_delta_usd=Decimal("5"),
        request_payload={"metadata": {"risk_level": "low"}},
    )
    default_trace = service._resolve_approval_routing_trace(
        policy=policy,
        decision=unmatched_decision,
    )
    assert default_trace["matched_rule"] == "default"


def test_routing_trace_or_default_uses_fallback_and_sanitizes_valid_trace() -> None:
    service = _service()
    tenant_id = uuid4()
    policy = EnforcementPolicy(
        tenant_id=tenant_id,
        enforce_nonprod_requester_reviewer_separation=False,
        approval_routing_rules=[],
    )
    decision = SimpleNamespace(environment="dev", request_payload={"metadata": {}}, action="terraform.apply", estimated_monthly_delta_usd=Decimal("10"))

    approval_missing = SimpleNamespace(routing_trace={"rule_id": "", "required_permission": None})
    fallback = service._routing_trace_or_default(
        policy=policy,
        decision=decision,
        approval=approval_missing,
    )
    assert fallback["matched_rule"] == "default"

    approval_valid = SimpleNamespace(
        routing_trace={
            "rule_id": "  custom-rule-id ",
            "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
            "allowed_reviewer_roles": ["member", "member", "owner"],
            "require_requester_reviewer_separation": True,
        }
    )
    sanitized = service._routing_trace_or_default(
        policy=policy,
        decision=decision,
        approval=approval_valid,
    )
    assert sanitized["rule_id"] == "custom-rule-id"
    assert sanitized["required_permission"] == APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
    assert sanitized["allowed_reviewer_roles"] == ["member", "owner"]
    assert sanitized["require_requester_reviewer_separation"] is True


def test_entitlement_waterfall_and_budget_waterfall_cover_mode_branches() -> None:
    service = _service()

    plan_fail = service._evaluate_entitlement_waterfall(
        mode=EnforcementMode.SHADOW,
        monthly_delta=Decimal("200"),
        plan_headroom=Decimal("100"),
        allocation_headroom=Decimal("100"),
        reserved_credit_headroom=Decimal("0"),
        emergency_credit_headroom=Decimal("0"),
        enterprise_headroom=None,
    )
    assert plan_fail.decision == EnforcementDecisionType.ALLOW
    assert plan_fail.reason_code == "plan_limit_exceeded"

    budget_soft = service._evaluate_entitlement_waterfall(
        mode=EnforcementMode.SOFT,
        monthly_delta=Decimal("300"),
        plan_headroom=None,
        allocation_headroom=Decimal("100"),
        reserved_credit_headroom=Decimal("100"),
        emergency_credit_headroom=Decimal("50"),
        enterprise_headroom=None,
    )
    assert budget_soft.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert budget_soft.reason_code == "budget_exceeded"
    assert budget_soft.reserve_allocation_usd == Decimal("100.0000")
    assert budget_soft.reserve_reserved_credit_usd == Decimal("100.0000")
    assert budget_soft.reserve_emergency_credit_usd == Decimal("50.0000")

    enterprise_soft = service._evaluate_entitlement_waterfall(
        mode=EnforcementMode.SOFT,
        monthly_delta=Decimal("250"),
        plan_headroom=None,
        allocation_headroom=Decimal("200"),
        reserved_credit_headroom=Decimal("100"),
        emergency_credit_headroom=Decimal("0"),
        enterprise_headroom=Decimal("200"),
    )
    assert enterprise_soft.decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert enterprise_soft.reason_code == "enterprise_ceiling_exceeded"

    allow_with_credits = service._evaluate_entitlement_waterfall(
        mode=EnforcementMode.HARD,
        monthly_delta=Decimal("150"),
        plan_headroom=None,
        allocation_headroom=Decimal("100"),
        reserved_credit_headroom=Decimal("50"),
        emergency_credit_headroom=Decimal("0"),
        enterprise_headroom=None,
    )
    assert allow_with_credits.decision == EnforcementDecisionType.ALLOW_WITH_CREDITS
    assert allow_with_credits.reason_code is None

    allow = service._evaluate_entitlement_waterfall(
        mode=EnforcementMode.HARD,
        monthly_delta=Decimal("80"),
        plan_headroom=None,
        allocation_headroom=Decimal("100"),
        reserved_credit_headroom=Decimal("0"),
        emergency_credit_headroom=Decimal("0"),
        enterprise_headroom=None,
    )
    assert allow.decision == EnforcementDecisionType.ALLOW
    assert allow.reason_code is None

    reasons: list[str] = []
    decision, reserved_alloc, reserved_credit = service._evaluate_budget_waterfall(
        mode=EnforcementMode.SOFT,
        monthly_delta=Decimal("220"),
        allocation_headroom=Decimal("100"),
        credits_headroom=Decimal("100"),
        reasons=reasons,
    )
    assert decision == EnforcementDecisionType.REQUIRE_APPROVAL
    assert reserved_alloc == Decimal("100.0000")
    assert reserved_credit == Decimal("100.0000")
    assert "budget_exceeded" in reasons
    assert "soft_mode_budget_escalation" in reasons
    assert "credit_waterfall_used" in reasons


def test_mode_violation_helpers_and_gate_result_response() -> None:
    service = _service()

    assert service._mode_violation_decision(EnforcementMode.SHADOW) == EnforcementDecisionType.ALLOW
    assert service._mode_violation_decision(EnforcementMode.SOFT) == EnforcementDecisionType.REQUIRE_APPROVAL
    assert service._mode_violation_decision(EnforcementMode.HARD) == EnforcementDecisionType.DENY

    assert service._mode_violation_reason_suffix(EnforcementMode.SHADOW, subject="budget") == "shadow_mode_budget_override"
    assert service._mode_violation_reason_suffix(EnforcementMode.SOFT, subject="budget") == "soft_mode_budget_escalation"
    assert service._mode_violation_reason_suffix(EnforcementMode.HARD, subject="budget") == "hard_mode_budget_closed"

    decision = SimpleNamespace(
        decision=EnforcementDecisionType.REQUIRE_APPROVAL,
        reason_codes=["budget_exceeded"],
        id=uuid4(),
        policy_version=7,
        approval_required=True,
        request_fingerprint="fingerprint-123",
        reservation_active=True,
        response_payload={"computed_context": {"risk_class": "high"}},
    )
    approval = SimpleNamespace(id=uuid4())
    result = GateEvaluationResult(
        decision=decision,
        approval=approval,
        approval_token="signed-token",
        ttl_seconds=600,
    )

    payload = gate_result_to_response(result)
    assert payload["decision"] == EnforcementDecisionType.REQUIRE_APPROVAL.value
    assert payload["approval_request_id"] == approval.id
    assert payload["approval_token"] == "signed-token"
    assert payload["computed_context"] == {"risk_class": "high"}

    decision.response_payload = {"computed_context": "invalid"}
    payload_no_context = gate_result_to_response(result)
    assert payload_no_context["computed_context"] is None


@pytest.mark.asyncio
async def test_acquire_gate_evaluation_lock_emits_contention_metrics(monkeypatch) -> None:
    class _Db:
        async def execute(self, _stmt):
            return SimpleNamespace(rowcount=1)

        async def rollback(self) -> None:
            raise AssertionError("rollback should not be called on successful lock acquisition")

    service = EnforcementService(db=_Db())
    policy = EnforcementPolicy(tenant_id=uuid4())
    policy.id = uuid4()
    lock_events = _FakeCounter()
    lock_wait = _FakeHistogram()
    perf_values = iter([100.0, 100.2])

    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL",
        lock_events,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_WAIT_SECONDS",
        lock_wait,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "_gate_lock_timeout_seconds",
        lambda: 1.0,
    )
    monkeypatch.setattr(
        enforcement_service_module.time,
        "perf_counter",
        lambda: next(perf_values),
    )

    await service._acquire_gate_evaluation_lock(
        policy=policy,
        source=EnforcementSource.TERRAFORM,
    )

    assert any(
        call[0]["event"] == "acquired" and call[0]["source"] == "terraform"
        for call in lock_events.calls
    )
    assert any(
        call[0]["event"] == "contended" and call[0]["source"] == "terraform"
        for call in lock_events.calls
    )
    assert len(lock_wait.calls) == 1
    assert lock_wait.calls[0][0]["source"] == "terraform"
    assert lock_wait.calls[0][0]["outcome"] == "acquired"
    assert lock_wait.calls[0][1] >= 0.19


@pytest.mark.asyncio
async def test_acquire_gate_evaluation_lock_rowcount_zero_raises_contended_reason(
    monkeypatch,
) -> None:
    class _Db:
        async def execute(self, _stmt):
            return SimpleNamespace(rowcount=0)

        async def rollback(self) -> None:
            raise AssertionError("rollback should not run for rowcount=0 path")

    service = EnforcementService(db=_Db())
    policy = EnforcementPolicy(tenant_id=uuid4())
    policy.id = uuid4()
    lock_events = _FakeCounter()
    lock_wait = _FakeHistogram()
    perf_values = iter([200.0, 200.01])

    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL",
        lock_events,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_WAIT_SECONDS",
        lock_wait,
    )
    monkeypatch.setattr(
        enforcement_service_module.time,
        "perf_counter",
        lambda: next(perf_values),
    )

    with pytest.raises(HTTPException) as exc:
        await service._acquire_gate_evaluation_lock(
            policy=policy,
            source=EnforcementSource.TERRAFORM,
        )

    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "gate_lock_contended"
    assert detail["lock_wait_seconds"] == "0.010"
    assert any(
        call[0]["event"] == "acquired" and call[0]["source"] == "terraform"
        for call in lock_events.calls
    )
    assert any(
        call[0]["event"] == "not_acquired" and call[0]["source"] == "terraform"
        for call in lock_events.calls
    )
    assert len(lock_wait.calls) == 1
    assert lock_wait.calls[0][0]["outcome"] == "acquired"


@pytest.mark.asyncio
async def test_acquire_gate_evaluation_lock_timeout_raises_lock_reason(monkeypatch) -> None:
    class _SlowDb:
        def __init__(self) -> None:
            self.rollback_calls = 0

        async def execute(self, _stmt):
            await asyncio.sleep(0.05)
            return SimpleNamespace(rowcount=1)

        async def rollback(self) -> None:
            self.rollback_calls += 1

    db = _SlowDb()
    service = EnforcementService(db=db)
    policy = EnforcementPolicy(tenant_id=uuid4())
    policy.id = uuid4()
    lock_events = _FakeCounter()
    lock_wait = _FakeHistogram()
    perf_values = iter([300.0, 300.05])

    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL",
        lock_events,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_WAIT_SECONDS",
        lock_wait,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "_gate_lock_timeout_seconds",
        lambda: 0.01,
    )
    monkeypatch.setattr(
        enforcement_service_module.time,
        "perf_counter",
        lambda: next(perf_values),
    )

    with pytest.raises(HTTPException) as exc:
        await service._acquire_gate_evaluation_lock(
            policy=policy,
            source=EnforcementSource.K8S_ADMISSION,
        )

    assert exc.value.status_code == 503
    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == "gate_lock_timeout"
    assert db.rollback_calls == 1
    assert any(
        call[0]["event"] == "timeout" and call[0]["source"] == "k8s_admission"
        for call in lock_events.calls
    )
    assert any(
        call[0]["event"] == "contended" and call[0]["source"] == "k8s_admission"
        for call in lock_events.calls
    )
    assert len(lock_wait.calls) == 1
    assert lock_wait.calls[0][0]["outcome"] == "timeout"


def test_policy_document_hash_and_gate_timeout_helper_branches(monkeypatch) -> None:
    assert enforcement_service_module._parse_iso_datetime("   ") is None

    december = datetime(2026, 12, 15, 9, 0, 0, tzinfo=timezone.utc)
    month_start, month_end = enforcement_service_module._month_bounds(december)
    assert month_start.month == 12
    assert month_end.month == 1
    assert month_end.year == 2027

    assert (
        enforcement_service_module._normalize_policy_document_schema_version(None)
        == "valdrix.enforcement.policy.v1"
    )
    assert len(
        enforcement_service_module._normalize_policy_document_schema_version("x" * 100)
    ) == 64
    assert (
        enforcement_service_module._normalize_policy_document_sha256("invalid")
        == "0" * 64
    )
    assert (
        enforcement_service_module._normalize_policy_document_sha256("g" * 64)
        == "0" * 64
    )
    assert enforcement_service_module._normalize_policy_document_sha256("a" * 64) == (
        "a" * 64
    )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS="bad"),
    )
    assert enforcement_service_module._gate_lock_timeout_seconds() == pytest.approx(1.6)

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS=0),
    )
    assert enforcement_service_module._gate_lock_timeout_seconds() == pytest.approx(0.05)

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS=1000),
    )
    assert enforcement_service_module._gate_lock_timeout_seconds() == pytest.approx(5.0)


def test_policy_document_contract_backfill_required_branches() -> None:
    service = _service()
    canonical_policy = enforcement_service_module.canonical_policy_document_payload(
        enforcement_service_module.PolicyDocument().model_dump(mode="json")
    )
    valid_hash = enforcement_service_module.policy_document_sha256(canonical_policy)
    valid_policy = SimpleNamespace(
        policy_document_schema_version=enforcement_service_module.POLICY_DOCUMENT_SCHEMA_VERSION,
        policy_document=canonical_policy,
        policy_document_sha256=valid_hash,
    )
    assert service._policy_document_contract_backfill_required(valid_policy) is False

    bad_schema = SimpleNamespace(
        policy_document_schema_version="legacy",
        policy_document=canonical_policy,
        policy_document_sha256=valid_hash,
    )
    assert service._policy_document_contract_backfill_required(bad_schema) is True

    non_mapping_policy_document = SimpleNamespace(
        policy_document_schema_version=enforcement_service_module.POLICY_DOCUMENT_SCHEMA_VERSION,
        policy_document="not-a-mapping",
        policy_document_sha256=valid_hash,
    )
    assert (
        service._policy_document_contract_backfill_required(non_mapping_policy_document)
        is True
    )

    invalid_policy_document = SimpleNamespace(
        policy_document_schema_version=enforcement_service_module.POLICY_DOCUMENT_SCHEMA_VERSION,
        policy_document={"schema_version": "invalid"},
        policy_document_sha256=valid_hash,
    )
    assert (
        service._policy_document_contract_backfill_required(invalid_policy_document)
        is True
    )

    invalid_hash = SimpleNamespace(
        policy_document_schema_version=enforcement_service_module.POLICY_DOCUMENT_SCHEMA_VERSION,
        policy_document=canonical_policy,
        policy_document_sha256="xyz",
    )
    assert service._policy_document_contract_backfill_required(invalid_hash) is True


def test_resolve_monthly_ceiling_none_and_positive_tier_limit_paths(monkeypatch) -> None:
    service = _service()
    tenant_id = uuid4()

    monkeypatch.setattr(
        enforcement_service_module,
        "get_tier_limit",
        lambda _tier, _key: None,
    )
    assert (
        asyncio.run(
            service._resolve_plan_monthly_ceiling_usd(
                policy=EnforcementPolicy(tenant_id=tenant_id, plan_monthly_ceiling_usd=None),
                tenant_tier=enforcement_service_module.PricingTier.PRO,
            )
        )
        is None
    )
    assert (
        asyncio.run(
            service._resolve_enterprise_monthly_ceiling_usd(
                policy=EnforcementPolicy(
                    tenant_id=tenant_id, enterprise_monthly_ceiling_usd=None
                ),
                tenant_tier=enforcement_service_module.PricingTier.PRO,
            )
        )
        is None
    )

    monkeypatch.setattr(
        enforcement_service_module,
        "get_tier_limit",
        lambda _tier, key: (
            Decimal("333.2222")
            if key == "enforcement_plan_monthly_ceiling_usd"
            else Decimal("777.4444")
        ),
    )
    assert asyncio.run(
        service._resolve_plan_monthly_ceiling_usd(
            policy=EnforcementPolicy(tenant_id=tenant_id, plan_monthly_ceiling_usd=None),
            tenant_tier=enforcement_service_module.PricingTier.PRO,
        )
    ) == Decimal("333.2222")
    assert asyncio.run(
        service._resolve_enterprise_monthly_ceiling_usd(
            policy=EnforcementPolicy(tenant_id=tenant_id, enterprise_monthly_ceiling_usd=None),
            tenant_tier=enforcement_service_module.PricingTier.PRO,
        )
    ) == Decimal("777.4444")


def test_extract_decision_risk_level_handles_missing_and_empty_metadata() -> None:
    service = _service()
    assert (
        service._extract_decision_risk_level(
            SimpleNamespace(request_payload={"metadata": "not-a-dict"})
        )
        is None
    )
    assert (
        service._extract_decision_risk_level(
            SimpleNamespace(request_payload={"metadata": {"risk_level": "", "risk": None}})
        )
        is None
    )


def test_resolve_approval_routing_trace_skips_unmatched_rules_and_falls_back_permission() -> None:
    service = _service()
    tenant_id = uuid4()
    policy = EnforcementPolicy(
        tenant_id=tenant_id,
        enforce_prod_requester_reviewer_separation=True,
        approval_routing_rules=[
            "not-a-rule",
            {"rule_id": "disabled", "enabled": False},
            {
                "rule_id": "action-miss",
                "action_prefixes": ["terraform.destroy"],
            },
            {
                "rule_id": "min-too-high",
                "min_monthly_delta_usd": "1000",
            },
            {
                "rule_id": "max-too-low",
                "max_monthly_delta_usd": "10",
            },
            {
                "rule_id": "risk-miss",
                "risk_levels": ["critical"],
            },
            {
                "rule_id": "matched",
                "required_permission": "invalid-permission",
                "allowed_reviewer_roles": ["member"],
            },
        ],
    )
    decision = SimpleNamespace(
        environment="prod",
        action="terraform.apply",
        estimated_monthly_delta_usd=Decimal("50"),
        request_payload={"metadata": {"risk_level": "high"}},
    )

    trace = service._resolve_approval_routing_trace(policy=policy, decision=decision)
    assert trace["matched_rule"] == "policy_rule"
    assert trace["rule_id"] == "matched"
    assert (
        trace["required_permission"]
        == APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )
    assert trace["allowed_reviewer_roles"] == ["member"]


def test_export_manifest_signing_secret_and_key_id_resolution(monkeypatch) -> None:
    service = _service()

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_SIGNING_SECRET="a" * 32,
            SUPABASE_JWT_SECRET="b" * 32,
            ENFORCEMENT_EXPORT_SIGNING_KID="explicit-kid",
            JWT_SIGNING_KID="jwt-kid",
        ),
    )
    assert service._resolve_export_manifest_signing_secret() == "a" * 32
    assert service._resolve_export_manifest_signing_key_id() == "explicit-kid"

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_SIGNING_SECRET="short",
            SUPABASE_JWT_SECRET="b" * 32,
            ENFORCEMENT_EXPORT_SIGNING_KID="",
            JWT_SIGNING_KID="jwt-kid",
        ),
    )
    assert service._resolve_export_manifest_signing_secret() == "b" * 32
    assert service._resolve_export_manifest_signing_key_id() == "jwt-kid"

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_SIGNING_SECRET="",
            SUPABASE_JWT_SECRET="",
            ENFORCEMENT_EXPORT_SIGNING_KID="",
            JWT_SIGNING_KID="",
        ),
    )
    with pytest.raises(HTTPException, match="not configured"):
        service._resolve_export_manifest_signing_secret()
    assert (
        service._resolve_export_manifest_signing_key_id()
        == "enforcement-export-hmac-v1"
    )


def test_render_approvals_csv_handles_non_list_roles() -> None:
    service = _service()
    now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
    approval = SimpleNamespace(
        id=uuid4(),
        decision_id=uuid4(),
        status=EnforcementApprovalStatus.PENDING,
        requested_by_user_id=uuid4(),
        reviewed_by_user_id=None,
        review_notes=None,
        routing_rule_id="rule-1",
        routing_trace={"required_permission": "perm", "allowed_reviewer_roles": "owner"},
        approval_token_expires_at=None,
        approval_token_consumed_at=None,
        expires_at=now + timedelta(minutes=5),
        approved_at=None,
        denied_at=None,
        created_at=now,
        updated_at=now,
    )
    csv_payload = service._render_approvals_csv([approval])
    rows = csv_payload.strip().splitlines()
    assert len(rows) == 2
    assert "routing_allowed_reviewer_roles" in rows[0]
    assert ",," in rows[1]


def test_decode_and_extract_approval_token_error_branches(monkeypatch) -> None:
    service = _service()
    with monkeypatch.context() as context:
        context.setattr(
            enforcement_service_module,
            "get_settings",
            lambda: SimpleNamespace(SUPABASE_JWT_SECRET="too-short", API_URL="https://api"),
        )
        with pytest.raises(HTTPException, match="not configured"):
            service._decode_approval_token("token")

    def _raise_expired(*_args, **_kwargs):
        raise enforcement_service_module.jwt.ExpiredSignatureError("expired")

    with monkeypatch.context() as context:
        context.setattr(
            enforcement_service_module,
            "get_settings",
            lambda: SimpleNamespace(
                SUPABASE_JWT_SECRET="s" * 32,
                ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS=[],
                API_URL="https://api",
            ),
        )
        context.setattr(enforcement_service_module.jwt, "decode", _raise_expired)
        with pytest.raises(HTTPException, match="expired"):
            service._decode_approval_token("token")

    base_payload = {
        "approval_id": str(uuid4()),
        "decision_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "project_id": "project",
        "source": EnforcementSource.TERRAFORM.value,
        "environment": "prod",
        "request_fingerprint": "a" * 64,
        "resource_reference": "module.db.aws_db_instance.main",
        "max_monthly_delta_usd": "10.0000",
        "max_hourly_delta_usd": "0.010000",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 600,
    }
    context = service._extract_token_context(base_payload)
    assert context.project_id == "project"

    bad_uuid_payload = dict(base_payload)
    bad_uuid_payload["approval_id"] = "not-uuid"
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_uuid_payload)

    bad_source_payload = dict(base_payload)
    bad_source_payload["source"] = "invalid"
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_source_payload)

    bad_exp_type_payload = dict(base_payload)
    bad_exp_type_payload["exp"] = object()
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_exp_type_payload)

    bad_exp_value_payload = dict(base_payload)
    bad_exp_value_payload["exp"] = "NaN"
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_exp_value_payload)

    bad_fingerprint_payload = dict(base_payload)
    bad_fingerprint_payload["request_fingerprint"] = "short"
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_fingerprint_payload)

    bad_resource_payload = dict(base_payload)
    bad_resource_payload["resource_reference"] = ""
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_resource_payload)

    bad_project_payload = dict(base_payload)
    bad_project_payload["project_id"] = ""
    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(bad_project_payload)


def test_build_approval_token_requires_secret_and_includes_kid(monkeypatch) -> None:
    service = _service()
    decision = SimpleNamespace(
        tenant_id=uuid4(),
        project_id="proj",
        id=uuid4(),
        source=EnforcementSource.TERRAFORM,
        environment="prod",
        request_fingerprint="b" * 64,
        estimated_monthly_delta_usd=Decimal("10.0000"),
        estimated_hourly_delta_usd=Decimal("0.010000"),
        resource_reference="module.app.aws_instance.main",
    )
    approval = SimpleNamespace(id=uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            SUPABASE_JWT_SECRET="short",
            API_URL="https://api.example.com",
            JWT_SIGNING_KID="kid-1",
        ),
    )
    with pytest.raises(HTTPException, match="not configured"):
        service._build_approval_token(
            decision=decision,
            approval=approval,
            expires_at=expires_at,
        )

    captured_headers: dict[str, str] = {}

    def _fake_encode(payload, secret, algorithm, headers=None):
        del payload, secret, algorithm
        nonlocal captured_headers
        captured_headers = dict(headers or {})
        return "signed-token"

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            SUPABASE_JWT_SECRET="s" * 32,
            API_URL="https://api.example.com",
            JWT_SIGNING_KID="kid-1",
        ),
    )
    monkeypatch.setattr(enforcement_service_module.jwt, "encode", _fake_encode)
    token = service._build_approval_token(
        decision=decision,
        approval=approval,
        expires_at=expires_at,
    )
    assert token == "signed-token"
    assert captured_headers == {"kid": "kid-1"}


@pytest.mark.asyncio
async def test_consume_approval_token_reject_matrix_covers_binding_and_expected_mismatches(
    monkeypatch,
) -> None:
    service = _service()
    token_events = _FakeCounter()
    fixed_now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
    tenant_id = uuid4()
    approval_id = uuid4()
    decision_id = uuid4()
    token_value = "approval-token"
    token_hash = enforcement_service_module.hashlib.sha256(
        token_value.encode("utf-8")
    ).hexdigest()

    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_APPROVAL_TOKEN_EVENTS_TOTAL",
        token_events,
    )
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)
    monkeypatch.setattr(service, "_decode_approval_token", lambda _token: {"sub": "stub"})

    state: dict[str, object] = {}

    def _base_token_context() -> SimpleNamespace:
        return SimpleNamespace(
            tenant_id=tenant_id,
            approval_id=approval_id,
            decision_id=decision_id,
            expires_at=fixed_now + timedelta(minutes=10),
            source=EnforcementSource.TERRAFORM,
            project_id="proj-alpha",
            environment="prod",
            request_fingerprint="f" * 64,
            resource_reference="module.db.aws_db_instance.main",
            max_monthly_delta_usd=Decimal("10.0000"),
            max_hourly_delta_usd=Decimal("0.010000"),
        )

    def _base_approval() -> SimpleNamespace:
        return SimpleNamespace(
            id=approval_id,
            status=EnforcementApprovalStatus.APPROVED,
            approval_token_hash=token_hash,
            approval_token_expires_at=fixed_now + timedelta(minutes=10),
            approval_token_consumed_at=None,
        )

    def _base_decision() -> SimpleNamespace:
        return SimpleNamespace(
            id=decision_id,
            source=EnforcementSource.TERRAFORM,
            project_id="proj-alpha",
            environment="prod",
            request_fingerprint="f" * 64,
            resource_reference="module.db.aws_db_instance.main",
            estimated_monthly_delta_usd=Decimal("10.0000"),
            estimated_hourly_delta_usd=Decimal("0.010000"),
            token_expires_at=None,
        )

    monkeypatch.setattr(
        service,
        "_extract_token_context",
        lambda _payload: state["token_context"],
    )

    async def _fake_load_approval_with_decision(*, tenant_id, approval_id):
        assert tenant_id == state["tenant_id"]
        assert approval_id == state["approval_id"]
        return state["approval"], state["decision"]

    monkeypatch.setattr(service, "_load_approval_with_decision", _fake_load_approval_with_decision)

    async def _assert_reject(
        *,
        expected_event: str,
        expected_status: int,
        expected_detail_substring: str,
        approval_token: str = token_value,
        mutate=None,
        kwargs: dict[str, object] | None = None,
    ) -> None:
        token_context = _base_token_context()
        approval = _base_approval()
        decision = _base_decision()
        if mutate is not None:
            mutate(token_context=token_context, approval=approval, decision=decision)
        state["tenant_id"] = tenant_id
        state["approval_id"] = approval_id
        state["token_context"] = token_context
        state["approval"] = approval
        state["decision"] = decision
        before = len(token_events.calls)
        with pytest.raises(HTTPException) as exc:
            await service.consume_approval_token(
                tenant_id=tenant_id,
                approval_token=approval_token,
                **(kwargs or {}),
            )
        assert exc.value.status_code == expected_status
        assert expected_detail_substring.lower() in str(exc.value.detail).lower()
        assert len(token_events.calls) == before + 1
        assert token_events.calls[-1][0]["event"] == expected_event

    await _assert_reject(
        expected_event="token_missing",
        expected_status=422,
        expected_detail_substring="required",
        approval_token="   ",
    )
    await _assert_reject(
        expected_event="decision_binding_mismatch",
        expected_status=409,
        expected_detail_substring="decision binding mismatch",
        mutate=lambda **objs: setattr(objs["token_context"], "decision_id", uuid4()),
    )
    await _assert_reject(
        expected_event="status_not_active",
        expected_status=409,
        expected_detail_substring="not active",
        mutate=lambda **objs: setattr(
            objs["approval"], "status", EnforcementApprovalStatus.DENIED
        ),
    )
    await _assert_reject(
        expected_event="token_hash_mismatch",
        expected_status=409,
        expected_detail_substring="token mismatch",
        mutate=lambda **objs: setattr(objs["approval"], "approval_token_hash", None),
    )
    await _assert_reject(
        expected_event="token_expired",
        expected_status=409,
        expected_detail_substring="expired",
        mutate=lambda **objs: setattr(
            objs["approval"], "approval_token_expires_at", fixed_now - timedelta(seconds=1)
        ),
    )
    await _assert_reject(
        expected_event="source_mismatch",
        expected_status=409,
        expected_detail_substring="source mismatch",
        mutate=lambda **objs: setattr(
            objs["token_context"], "source", EnforcementSource.K8S_ADMISSION
        ),
    )
    await _assert_reject(
        expected_event="environment_mismatch",
        expected_status=409,
        expected_detail_substring="environment mismatch",
        mutate=lambda **objs: setattr(objs["token_context"], "environment", "staging"),
    )
    await _assert_reject(
        expected_event="fingerprint_mismatch",
        expected_status=409,
        expected_detail_substring="fingerprint mismatch",
        mutate=lambda **objs: setattr(objs["token_context"], "request_fingerprint", "a" * 64),
    )
    await _assert_reject(
        expected_event="resource_binding_mismatch",
        expected_status=409,
        expected_detail_substring="resource binding mismatch",
        mutate=lambda **objs: setattr(
            objs["token_context"], "resource_reference", "module.other.aws_db_instance.main"
        ),
    )
    await _assert_reject(
        expected_event="cost_binding_mismatch",
        expected_status=409,
        expected_detail_substring="cost binding mismatch",
        mutate=lambda **objs: setattr(
            objs["token_context"], "max_monthly_delta_usd", Decimal("11.0000")
        ),
    )
    await _assert_reject(
        expected_event="expected_source_mismatch",
        expected_status=409,
        expected_detail_substring="Expected source mismatch",
        kwargs={"expected_source": EnforcementSource.K8S_ADMISSION},
    )
    await _assert_reject(
        expected_event="expected_project_mismatch",
        expected_status=409,
        expected_detail_substring="Expected project mismatch",
        kwargs={"expected_project_id": "proj-other"},
    )
    await _assert_reject(
        expected_event="expected_environment_mismatch",
        expected_status=409,
        expected_detail_substring="Expected environment mismatch",
        kwargs={"expected_environment": "nonprod"},
    )
    await _assert_reject(
        expected_event="expected_fingerprint_mismatch",
        expected_status=409,
        expected_detail_substring="Expected request fingerprint mismatch",
        kwargs={"expected_request_fingerprint": "e" * 64},
    )


@pytest.mark.asyncio
async def test_acquire_gate_evaluation_lock_error_and_not_acquired_branches(
    monkeypatch,
) -> None:
    class _ErrorDb:
        async def execute(self, _stmt):
            raise RuntimeError("db failure")

        async def rollback(self) -> None:
            return None

    class _NoLockDb:
        async def execute(self, _stmt):
            return SimpleNamespace(rowcount=0)

        async def rollback(self) -> None:
            return None

    policy = EnforcementPolicy(tenant_id=uuid4())
    policy.id = uuid4()

    lock_events = _FakeCounter()
    lock_wait = _FakeHistogram()
    perf_values = iter([700.0, 700.1, 800.0, 800.01])
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_EVENTS_TOTAL",
        lock_events,
    )
    monkeypatch.setattr(
        enforcement_service_module,
        "ENFORCEMENT_GATE_LOCK_WAIT_SECONDS",
        lock_wait,
    )
    monkeypatch.setattr(
        enforcement_service_module.time,
        "perf_counter",
        lambda: next(perf_values),
    )

    error_service = EnforcementService(db=_ErrorDb())
    with pytest.raises(RuntimeError, match="db failure"):
        await error_service._acquire_gate_evaluation_lock(
            policy=policy,
            source=EnforcementSource.TERRAFORM,
        )
    assert any(call[0]["event"] == "error" for call in lock_events.calls)

    nolock_service = EnforcementService(db=_NoLockDb())
    with pytest.raises(HTTPException, match="Unable to acquire enforcement gate evaluation lock"):
        await nolock_service._acquire_gate_evaluation_lock(
            policy=policy,
            source=EnforcementSource.TERRAFORM,
        )
    assert any(call[0]["event"] == "not_acquired" for call in lock_events.calls)


@pytest.mark.asyncio
async def test_reserve_credit_from_grants_zero_target_and_insufficient_headroom() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, row_batches: list[list[SimpleNamespace]]) -> None:
            self._row_batches = list(row_batches)
            self.added: list[object] = []

        async def execute(self, _stmt):
            return _Rows(self._row_batches.pop(0))

        def add(self, obj: object) -> None:
            self.added.append(obj)

    tenant_id = uuid4()
    decision_id = uuid4()
    now = datetime.now(timezone.utc)
    zero_remaining_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("0"),
        total_amount_usd=Decimal("100"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    partial_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("1"),
        total_amount_usd=Decimal("100"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    full_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("5"),
        total_amount_usd=Decimal("100"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    trailing_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("2"),
        total_amount_usd=Decimal("100"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    db = _Db([[zero_remaining_grant, partial_grant], [full_grant, trailing_grant]])
    service = EnforcementService(db=db)

    assert (
        await service._reserve_credit_from_grants(
            tenant_id=tenant_id,
            decision_id=decision_id,
            scope_key="default",
            pool_type=EnforcementCreditPoolType.RESERVED,
            reserve_target_usd=Decimal("0"),
            now=now,
        )
        == []
    )

    with pytest.raises(HTTPException, match="Insufficient credit grant headroom"):
        await service._reserve_credit_from_grants(
            tenant_id=tenant_id,
            decision_id=decision_id,
            scope_key="default",
            pool_type=EnforcementCreditPoolType.RESERVED,
            reserve_target_usd=Decimal("5"),
            now=now,
        )

    allocations = await service._reserve_credit_from_grants(
        tenant_id=tenant_id,
        decision_id=decision_id,
        scope_key="default",
        pool_type=EnforcementCreditPoolType.RESERVED,
        reserve_target_usd=Decimal("1"),
        now=now,
    )
    assert len(allocations) == 1


@pytest.mark.asyncio
async def test_reserve_credit_from_grants_skips_subquantum_reserve_amount() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, row_batches: list[list[SimpleNamespace]]) -> None:
            self._row_batches = list(row_batches)
            self.added: list[object] = []

        async def execute(self, _stmt):
            return _Rows(self._row_batches.pop(0))

        def add(self, obj: object) -> None:
            self.added.append(obj)

    tenant_id = uuid4()
    decision_id = uuid4()
    now = datetime.now(timezone.utc)
    subquantum_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("0.00004"),
        total_amount_usd=Decimal("1.0000"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    usable_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("0.0002"),
        total_amount_usd=Decimal("1.0000"),
        active=True,
        expires_at=None,
        created_at=now,
    )
    db = _Db([[subquantum_grant, usable_grant]])
    service = EnforcementService(db=db)

    allocations = await service._reserve_credit_from_grants(
        tenant_id=tenant_id,
        decision_id=decision_id,
        scope_key="default",
        pool_type=EnforcementCreditPoolType.RESERVED,
        reserve_target_usd=Decimal("0.0001"),
        now=now,
    )

    assert len(allocations) == 1
    assert allocations[0]["credit_grant_id"] == str(usable_grant.id)
    assert allocations[0]["reserved_amount_usd"] == "0.0001"
    assert subquantum_grant.remaining_amount_usd == Decimal("0.00004")
    assert usable_grant.remaining_amount_usd == Decimal("0.0001")
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_settle_credit_reservations_for_decision_missing_grant_and_drift_errors() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, row_batches: list[list[SimpleNamespace]]) -> None:
            self._row_batches = list(row_batches)

        async def execute(self, _stmt):
            return _Rows(self._row_batches.pop(0))

    tenant_id = uuid4()
    now = datetime.now(timezone.utc)

    missing_grant_allocation = SimpleNamespace(
        id=uuid4(),
        credit_grant_id=uuid4(),
        credit_pool_type=EnforcementCreditPoolType.RESERVED,
        reserved_amount_usd=Decimal("0.5000"),
        consumed_amount_usd=Decimal("0"),
        released_amount_usd=Decimal("0"),
        active=True,
        settled_at=None,
        created_at=now,
    )
    missing_grant_service = EnforcementService(db=_Db([[missing_grant_allocation], []]))
    with pytest.raises(HTTPException, match="Missing credit grant row for reservation allocation"):
        await missing_grant_service._settle_credit_reservations_for_decision(
            tenant_id=tenant_id,
            decision=SimpleNamespace(id=uuid4(), reserved_credit_usd=Decimal("0.5000")),
            consumed_credit_usd=Decimal("0.2500"),
            now=now,
        )

    drift_grant = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("0.0000"),
        total_amount_usd=Decimal("1.0000"),
        expires_at=None,
        active=True,
    )
    drift_allocation = SimpleNamespace(
        id=uuid4(),
        credit_grant_id=drift_grant.id,
        credit_pool_type=EnforcementCreditPoolType.RESERVED,
        reserved_amount_usd=Decimal("0.5000"),
        consumed_amount_usd=Decimal("0"),
        released_amount_usd=Decimal("0"),
        active=True,
        settled_at=None,
        created_at=now,
    )
    drift_service = EnforcementService(db=_Db([[drift_allocation], [drift_grant]]))
    with pytest.raises(HTTPException, match="Credit reservation settlement drift detected"):
        await drift_service._settle_credit_reservations_for_decision(
            tenant_id=tenant_id,
            decision=SimpleNamespace(id=uuid4(), reserved_credit_usd=Decimal("1.0000")),
            consumed_credit_usd=Decimal("0"),
            now=now,
        )


@pytest.mark.asyncio
async def test_settle_credit_reservations_for_decision_clamps_release_and_grant_total() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, row_batches: list[list[SimpleNamespace]]) -> None:
            self._row_batches = list(row_batches)

        async def execute(self, _stmt):
            return _Rows(self._row_batches.pop(0))

    tenant_id = uuid4()
    now = datetime.now(timezone.utc)
    grant_one = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("0.1000"),
        total_amount_usd=Decimal("10.0000"),
        expires_at=None,
        active=True,
    )
    grant_two = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        remaining_amount_usd=Decimal("9.9000"),
        total_amount_usd=Decimal("10.0000"),
        expires_at=None,
        active=True,
    )
    allocation_one = SimpleNamespace(
        id=uuid4(),
        credit_grant_id=grant_one.id,
        credit_pool_type=EnforcementCreditPoolType.RESERVED,
        reserved_amount_usd=Decimal("0.7500"),
        consumed_amount_usd=Decimal("0"),
        released_amount_usd=Decimal("0"),
        active=True,
        settled_at=None,
        created_at=now,
    )
    allocation_two = SimpleNamespace(
        id=uuid4(),
        credit_grant_id=grant_two.id,
        credit_pool_type=EnforcementCreditPoolType.EMERGENCY,
        reserved_amount_usd=Decimal("0.7500"),
        consumed_amount_usd=Decimal("0"),
        released_amount_usd=Decimal("0"),
        active=True,
        settled_at=None,
        created_at=now,
    )
    service = EnforcementService(db=_Db([[allocation_one, allocation_two], [grant_one, grant_two]]))

    diagnostics = await service._settle_credit_reservations_for_decision(
        tenant_id=tenant_id,
        decision=SimpleNamespace(id=uuid4(), reserved_credit_usd=Decimal("1.0000")),
        consumed_credit_usd=Decimal("0.7500"),
        now=now,
    )

    assert len(diagnostics) == 2
    assert diagnostics[0]["released_amount_usd"] == "0.0000"
    assert diagnostics[1]["released_amount_usd"] == "0.2500"
    assert diagnostics[1]["grant_remaining_amount_usd_after"] == "10.0000"
    assert allocation_one.consumed_amount_usd == Decimal("0.7500")
    assert allocation_one.released_amount_usd == Decimal("0.0000")
    assert allocation_two.consumed_amount_usd == Decimal("0.0000")
    assert allocation_two.released_amount_usd == Decimal("0.2500")
    assert allocation_one.active is False
    assert allocation_two.active is False
    assert grant_two.remaining_amount_usd == Decimal("10.0000")


@pytest.mark.asyncio
async def test_load_approval_with_decision_and_assert_pending_error_paths() -> None:
    class _Result:
        def __init__(self, value) -> None:
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Db:
        def __init__(self, values: list[object | None]) -> None:
            self._values = list(values)

        async def execute(self, _stmt):
            return _Result(self._values.pop(0))

    tenant_id = uuid4()
    approval_id = uuid4()

    service_missing_approval = EnforcementService(db=_Db([None]))
    with pytest.raises(HTTPException, match="Approval request not found"):
        await service_missing_approval._load_approval_with_decision(
            tenant_id=tenant_id,
            approval_id=approval_id,
        )

    approval = SimpleNamespace(
        id=approval_id,
        tenant_id=tenant_id,
        decision_id=uuid4(),
        status=EnforcementApprovalStatus.PENDING,
    )
    service_missing_decision = EnforcementService(db=_Db([approval, None]))
    with pytest.raises(HTTPException, match="Approval decision not found"):
        await service_missing_decision._load_approval_with_decision(
            tenant_id=tenant_id,
            approval_id=approval_id,
        )

    service = _service()
    with pytest.raises(HTTPException, match="already approved"):
        service._assert_pending(
            SimpleNamespace(status=EnforcementApprovalStatus.APPROVED)
        )


@pytest.mark.asyncio
async def test_enforce_reviewer_authority_updates_routing_trace_and_rejects_missing_permission(
    monkeypatch,
) -> None:
    service = _service()
    tenant_id = uuid4()
    policy = EnforcementPolicy(tenant_id=tenant_id, approval_routing_rules=[])
    approval = SimpleNamespace(
        routing_rule_id=None,
        routing_trace=None,
        requested_by_user_id=uuid4(),
    )
    decision = SimpleNamespace(
        environment="prod",
        action="terraform.apply",
        estimated_monthly_delta_usd=Decimal("100"),
        request_payload={"metadata": {"risk_level": "medium"}},
    )
    reviewer = SimpleNamespace(id=uuid4(), role="member")
    routing_trace = {
        "rule_id": "  explicit-rule  ",
        "required_permission": None,
        "allowed_reviewer_roles": ["member"],
        "require_requester_reviewer_separation": False,
    }

    monkeypatch.setattr(service, "_routing_trace_or_default", lambda **_kwargs: dict(routing_trace))

    async def _unexpected_permission_check(*_args, **_kwargs):
        raise AssertionError("permission lookup should not run when required_permission is missing")

    monkeypatch.setattr(
        enforcement_service_module,
        "user_has_approval_permission",
        _unexpected_permission_check,
    )

    with pytest.raises(HTTPException, match="missing required_permission") as exc:
        await service._enforce_reviewer_authority(
            tenant_id=tenant_id,
            policy=policy,
            approval=approval,
            decision=decision,
            reviewer=reviewer,
            enforce_requester_separation=False,
        )

    assert exc.value.status_code == 409
    assert approval.routing_rule_id == "explicit-rule"
    assert approval.routing_trace == routing_trace


@pytest.mark.asyncio
async def test_credit_headroom_helpers_cover_legacy_uncovered_and_spillover_paths() -> None:
    class _ScalarResult:
        def __init__(self, value: object) -> None:
            self._value = value

        def scalar_one(self) -> object:
            return self._value

    class _Db:
        def __init__(self, values: list[object]) -> None:
            self._values = list(values)

        async def execute(self, _stmt):
            return _ScalarResult(self._values.pop(0))

    tenant_id = uuid4()
    now = datetime.now(timezone.utc)

    # Legacy uncovered reservation exceeds reserved headroom and spills into emergency.
    service = EnforcementService(
        db=_Db([Decimal("5"), Decimal("3"), Decimal("10"), Decimal("2")])
    )
    reserved, emergency = await service._get_credit_headrooms(
        tenant_id=tenant_id,
        scope_key=" Prod ",
        now=now,
    )
    assert reserved == Decimal("0.0000")
    assert emergency == Decimal("0.0000")

    # Legacy uncovered reservation is fully absorbed by reserved pool; emergency untouched.
    service = EnforcementService(
        db=_Db([Decimal("10"), Decimal("4"), Decimal("12"), Decimal("10")])
    )
    reserved, emergency = await service._get_credit_headrooms(
        tenant_id=tenant_id,
        scope_key="default",
        now=now,
    )
    assert reserved == Decimal("8.0000")
    assert emergency == Decimal("4.0000")

    # No uncovered legacy reservation; branch should bypass legacy reduction entirely.
    service = EnforcementService(
        db=_Db([Decimal("7"), Decimal("2"), Decimal("4"), Decimal("4")])
    )
    reserved, emergency = await service._get_credit_headrooms(
        tenant_id=tenant_id,
        scope_key="default",
        now=now,
    )
    assert reserved == Decimal("7.0000")
    assert emergency == Decimal("2.0000")


@pytest.mark.asyncio
async def test_active_headroom_and_reserve_credit_for_decision_helper_branches(
    monkeypatch,
) -> None:
    service = _service()
    tenant_id = uuid4()
    decision_id = uuid4()
    now = datetime.now(timezone.utc)

    async def _fake_headrooms(**_kwargs):
        return (Decimal("1.23456"), Decimal("2.00005"))

    monkeypatch.setattr(service, "_get_credit_headrooms", _fake_headrooms)
    total = await service._get_active_credit_headroom(
        tenant_id=tenant_id,
        scope_key="default",
        now=now,
    )
    assert total == Decimal("3.2346")

    reserve_calls: list[dict[str, object]] = []

    async def _fake_reserve(**kwargs):
        reserve_calls.append(dict(kwargs))
        pool_type = kwargs["pool_type"]
        if pool_type == EnforcementCreditPoolType.RESERVED:
            return [{"pool_type": "reserved"}]
        return [{"pool_type": "emergency"}]

    monkeypatch.setattr(service, "_reserve_credit_from_grants", _fake_reserve)
    allocations = await service._reserve_credit_for_decision(
        tenant_id=tenant_id,
        decision_id=decision_id,
        scope_key=" PROD ",
        reserve_reserved_credit_usd=Decimal("1"),
        reserve_emergency_credit_usd=Decimal("2"),
        now=now,
    )
    emergency_only = await service._reserve_credit_for_decision(
        tenant_id=tenant_id,
        decision_id=decision_id,
        scope_key="default",
        reserve_reserved_credit_usd=Decimal("0"),
        reserve_emergency_credit_usd=Decimal("1"),
        now=now,
    )
    reserved_only = await service._reserve_credit_for_decision(
        tenant_id=tenant_id,
        decision_id=decision_id,
        scope_key="default",
        reserve_reserved_credit_usd=Decimal("1"),
        reserve_emergency_credit_usd=Decimal("0"),
        now=now,
    )

    assert allocations == [{"pool_type": "reserved"}, {"pool_type": "emergency"}]
    assert emergency_only == [{"pool_type": "emergency"}]
    assert reserved_only == [{"pool_type": "reserved"}]
    assert reserve_calls[0]["scope_key"] == "prod"
    assert reserve_calls[0]["pool_type"] == EnforcementCreditPoolType.RESERVED
    assert reserve_calls[1]["pool_type"] == EnforcementCreditPoolType.EMERGENCY
    assert reserve_calls[2]["pool_type"] == EnforcementCreditPoolType.EMERGENCY
    assert reserve_calls[3]["pool_type"] == EnforcementCreditPoolType.RESERVED


def test_decode_approval_token_deduplicates_candidate_secrets(monkeypatch) -> None:
    service = _service()
    decode_attempts: list[str] = []

    def _fake_decode(_token, secret, **_kwargs):
        decode_attempts.append(secret)
        if secret == "a" * 32:
            raise enforcement_service_module.jwt.InvalidTokenError("bad primary")
        return {"ok": True}

    monkeypatch.setattr(
        enforcement_service_module,
        "get_settings",
        lambda: SimpleNamespace(
            SUPABASE_JWT_SECRET="a" * 32,
            ENFORCEMENT_APPROVAL_TOKEN_FALLBACK_SECRETS=["a" * 32, "b" * 32, "b" * 32],
            API_URL="https://api.example.com",
        ),
    )
    monkeypatch.setattr(enforcement_service_module.jwt, "decode", _fake_decode)

    payload = service._decode_approval_token("token")
    assert payload == {"ok": True}
    assert decode_attempts == ["a" * 32, "b" * 32]


def test_extract_token_context_rejects_invalid_decimal_claims() -> None:
    service = _service()
    payload = {
        "approval_id": str(uuid4()),
        "decision_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "project_id": "project",
        "source": EnforcementSource.TERRAFORM.value,
        "environment": "prod",
        "request_fingerprint": "a" * 64,
        "resource_reference": "module.db.aws_db_instance.main",
        "max_monthly_delta_usd": "Infinity",
        "max_hourly_delta_usd": "0.010000",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 600,
    }

    with pytest.raises(HTTPException, match="Invalid approval token"):
        service._extract_token_context(payload)


@pytest.mark.asyncio
async def test_list_helpers_cover_active_reservations_and_decision_ledger_filters() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, row_batches: list[list[object]]) -> None:
            self._row_batches = list(row_batches)

        async def execute(self, _stmt):
            return _Rows(self._row_batches.pop(0))

    tenant_id = uuid4()
    reservation_a = SimpleNamespace(id=uuid4())
    reservation_b = SimpleNamespace(id=uuid4())
    ledger_a = SimpleNamespace(id=uuid4(), recorded_at=datetime.now(timezone.utc))
    ledger_b = SimpleNamespace(id=uuid4(), recorded_at=datetime.now(timezone.utc))
    service = EnforcementService(
        db=_Db(
            [
                [reservation_a, reservation_b],
                [ledger_a, ledger_b],
            ]
        )
    )

    active = await service.list_active_reservations(tenant_id=tenant_id, limit=5000)
    assert active == [reservation_a, reservation_b]

    ledger = await service.list_decision_ledger(
        tenant_id=tenant_id,
        limit=9999,
        start_at=datetime(2026, 2, 26, 0, 0, 0),  # naive -> _as_utc path
        end_at=datetime(2026, 2, 26, 23, 59, 59, tzinfo=timezone.utc),
    )
    assert [entry.entry for entry in ledger] == [ledger_a, ledger_b]


@pytest.mark.asyncio
async def test_list_reconciliation_exceptions_covers_filtering_fallbacks_and_limit_break() -> None:
    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _Db:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        async def execute(self, _stmt):
            return _Rows(self._rows)

    tenant_id = uuid4()
    base_time = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
    decision_without_reconciliation = SimpleNamespace(
        id=uuid4(),
        created_at=base_time,
        response_payload={"reservation_reconciliation": "not-a-dict"},
    )
    decision_zero_drift = SimpleNamespace(
        id=uuid4(),
        created_at=base_time - timedelta(minutes=1),
        response_payload={
            "reservation_reconciliation": {
                "drift_usd": "0",
                "expected_reserved_usd": "5",
                "actual_monthly_delta_usd": "5",
            }
        },
    )
    decision_savings_non_list_credit = SimpleNamespace(
        id=uuid4(),
        created_at=base_time - timedelta(minutes=2),
        response_payload={
            "reservation_reconciliation": {
                "drift_usd": "-1.2500",
                "status": "unexpected",
                "expected_reserved_usd": "10",
                "actual_monthly_delta_usd": "8.7500",
                "reconciled_at": "2026-02-26T10:00:00Z",
                "notes": "  saved money  ",
                "credit_settlement": "not-a-list",
            }
        },
    )
    decision_overage_list_credit = SimpleNamespace(
        id=uuid4(),
        created_at=base_time - timedelta(minutes=3),
        response_payload={
            "reservation_reconciliation": {
                "drift_usd": "1.5000",
                "status": "",
                "expected_reserved_usd": "6",
                "actual_monthly_delta_usd": "7.5000",
                "reconciled_at": None,
                "notes": None,
                "credit_settlement": [
                    "skip-me",
                    {" ": "drop", "pool": "reserved", "amount": Decimal("1.25")},
                ],
            }
        },
    )
    service = EnforcementService(
        db=_Db(
            [
                decision_without_reconciliation,
                decision_zero_drift,
                decision_savings_non_list_credit,
                decision_overage_list_credit,
            ]
        )
    )

    exceptions = await service.list_reconciliation_exceptions(
        tenant_id=tenant_id,
        limit=2,  # force line 2904 break after second exception append
    )

    assert len(exceptions) == 2
    assert [item.decision.id for item in exceptions] == [
        decision_savings_non_list_credit.id,
        decision_overage_list_credit.id,
    ]
    assert exceptions[0].status == "savings"
    assert exceptions[0].notes == "saved money"
    assert exceptions[0].credit_settlement == []
    assert exceptions[1].status == "overage"
    assert exceptions[1].notes is None
    assert exceptions[1].credit_settlement == [{"pool": "reserved", "amount": "1.25"}]


def test_build_reservation_reconciliation_idempotent_replay_reject_branches() -> None:
    service = _service()
    decision_id = uuid4()

    base_reconciliation = {
        "idempotency_key": "idem-1",
        "actual_monthly_delta_usd": "12.5000",
        "notes": "match-notes",
        "status": "matched",
        "drift_usd": "0.0000",
        "expected_reserved_usd": "12.5000",
        "reconciled_at": "2026-02-26T11:00:00Z",
    }

    # line 2923: reservation_reconciliation is not a mapping
    result = service._build_reservation_reconciliation_idempotent_replay(
        decision=SimpleNamespace(
            id=decision_id,
            response_payload={"reservation_reconciliation": "invalid"},
        ),
        actual_monthly_delta_usd=Decimal("12.5000"),
        notes="match-notes",
        idempotency_key="idem-1",
    )
    assert result is None

    # line 2927: stored idempotency key missing/mismatch
    result = service._build_reservation_reconciliation_idempotent_replay(
        decision=SimpleNamespace(
            id=decision_id,
            response_payload={"reservation_reconciliation": {**base_reconciliation, "idempotency_key": "other"}},
        ),
        actual_monthly_delta_usd=Decimal("12.5000"),
        notes="match-notes",
        idempotency_key="idem-1",
    )
    assert result is None

    # line 2948: notes mismatch conflict
    with pytest.raises(HTTPException, match="payload mismatch .*notes"):
        service._build_reservation_reconciliation_idempotent_replay(
            decision=SimpleNamespace(
                id=decision_id,
                response_payload={"reservation_reconciliation": dict(base_reconciliation)},
            ),
            actual_monthly_delta_usd=Decimal("12.5000"),
            notes="different-notes",
            idempotency_key="idem-1",
        )

    # line 2958: invalid stored status for replay
    with pytest.raises(HTTPException, match="invalid .*status"):
        service._build_reservation_reconciliation_idempotent_replay(
            decision=SimpleNamespace(
                id=decision_id,
                response_payload={
                    "reservation_reconciliation": {
                        **base_reconciliation,
                        "notes": None,
                        "status": "corrupt",
                    }
                },
            ),
            actual_monthly_delta_usd=Decimal("12.5000"),
            notes=None,
            idempotency_key="idem-1",
        )


@pytest.mark.asyncio
async def test_reconcile_reservation_early_error_branches_and_overdue_empty_fast_path(
    monkeypatch,
) -> None:
    class _ScalarResult:
        def __init__(self, value) -> None:
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class _Rows:
        def __init__(self, rows) -> None:
            self._rows = list(rows)

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self._rows))

    class _CursorResult:
        def __init__(self, rowcount: int) -> None:
            self.rowcount = rowcount

    class _Db:
        def __init__(self, results: list[object]) -> None:
            self._results = list(results)
            self.rollback_calls = 0

        async def execute(self, _stmt):
            return self._results.pop(0)

        async def rollback(self) -> None:
            self.rollback_calls += 1

    tenant_id = uuid4()
    actor_id = uuid4()
    decision_id = uuid4()

    # line 3000: decision not found on initial lookup
    not_found_service = EnforcementService(db=_Db([_ScalarResult(None)]))
    with pytest.raises(HTTPException, match="Decision not found") as exc:
        await not_found_service.reconcile_reservation(
            tenant_id=tenant_id,
            decision_id=decision_id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("1"),
            notes=None,
        )
    assert exc.value.status_code == 404

    # line 3004: negative actual rejected after lookup
    negative_service = EnforcementService(
        db=_Db([_ScalarResult(SimpleNamespace(reservation_active=True))])
    )
    with pytest.raises(HTTPException, match="must be >= 0") as exc:
        await negative_service.reconcile_reservation(
            tenant_id=tenant_id,
            decision_id=decision_id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("-0.0001"),
            notes=None,
        )
    assert exc.value.status_code == 422

    # line 3049: claim loses race and refreshed row no longer exists
    claim_miss_db = _Db(
        [
            _ScalarResult(SimpleNamespace(reservation_active=True)),
            _CursorResult(0),
            _ScalarResult(None),
        ]
    )
    claim_miss_service = EnforcementService(db=claim_miss_db)
    with pytest.raises(HTTPException, match="Decision not found") as exc:
        await claim_miss_service.reconcile_reservation(
            tenant_id=tenant_id,
            decision_id=decision_id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("1"),
            notes=None,
        )
    assert exc.value.status_code == 404
    assert claim_miss_db.rollback_calls == 1

    # line 3062: claim loses race, refreshed row exists but is inactive with no replay payload/key
    refreshed_inactive = SimpleNamespace(reservation_active=False)
    inactive_db = _Db(
        [
            _ScalarResult(SimpleNamespace(reservation_active=True)),
            _CursorResult(0),
            _ScalarResult(refreshed_inactive),
        ]
    )
    inactive_service = EnforcementService(db=inactive_db)
    with pytest.raises(HTTPException, match="Reservation is not active") as exc:
        await inactive_service.reconcile_reservation(
            tenant_id=tenant_id,
            decision_id=decision_id,
            actor_id=actor_id,
            actual_monthly_delta_usd=Decimal("1"),
            notes=None,
        )
    assert exc.value.status_code == 409
    assert inactive_db.rollback_calls == 1

    # line 3176: overdue scan returns empty set fast-path
    fixed_now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(enforcement_service_module, "_utcnow", lambda: fixed_now)
    overdue_service = EnforcementService(db=_Db([_Rows([])]))
    summary = await overdue_service.reconcile_overdue_reservations(
        tenant_id=tenant_id,
        actor_id=actor_id,
        older_than_seconds=30,  # bounded to 60
        limit=0,  # bounded to 1
    )
    assert summary.released_count == 0
    assert summary.total_released_usd == Decimal("0.0000")
    assert summary.decision_ids == []
    assert summary.older_than_seconds == 60
