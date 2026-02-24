from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import io
import json
from unittest.mock import patch
from uuid import UUID, uuid4
import zipfile

import pytest
from sqlalchemy import select

from app.models.enforcement import EnforcementDecision
from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import User
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.models.tenant import Tenant, UserRole
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.approval_permissions import (
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


class _FakeHistogram:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._last_labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeHistogram":
        self._last_labels = dict(labels)
        return self

    def observe(self, amount: float) -> None:
        self.calls.append((dict(self._last_labels), float(amount)))


async def _seed_tenant(db) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="Enforcement API Tenant",
        plan="enterprise",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


def _override_user(async_client, user: CurrentUser) -> None:
    async_client.app.dependency_overrides[get_current_user] = lambda: user


def _clear_user_override(async_client) -> None:
    async_client.app.dependency_overrides.pop(get_current_user, None)


async def _issue_approved_token_via_api(async_client) -> tuple[str, str, str]:
    policy = await async_client.post(
        "/api/v1/enforcement/policies",
        json={
            "terraform_mode": "soft",
            "k8s_admission_mode": "soft",
            "require_approval_for_prod": True,
            "require_approval_for_nonprod": False,
            "auto_approve_below_monthly_usd": "0",
            "hard_deny_above_monthly_usd": "2500",
            "default_ttl_seconds": 1200,
        },
    )
    assert policy.status_code == 200

    budget = await async_client.post(
        "/api/v1/enforcement/budgets",
        json={
            "scope_key": "default",
            "monthly_limit_usd": "2000",
            "active": True,
        },
    )
    assert budget.status_code == 200

    gate = await async_client.post(
        "/api/v1/enforcement/gate/terraform",
        json={
            "project_id": "default",
            "environment": "prod",
            "action": "terraform.apply",
            "resource_reference": "module.db.aws_db_instance.main",
            "estimated_monthly_delta_usd": "100",
            "estimated_hourly_delta_usd": "0.14",
            "metadata": {"resource_type": "aws_db_instance"},
            "idempotency_key": "api-token-consume-1",
        },
    )
    assert gate.status_code == 200
    gate_payload = gate.json()
    assert gate_payload["approval_request_id"] is not None

    approve = await async_client.post(
        f"/api/v1/enforcement/approvals/{gate_payload['approval_request_id']}/approve",
        json={"notes": "approved for token consume"},
    )
    assert approve.status_code == 200
    approve_payload = approve.json()
    assert isinstance(approve_payload["approval_token"], str)

    return (
        approve_payload["approval_token"],
        gate_payload["approval_request_id"],
        gate_payload["decision_id"],
    )


async def _set_terraform_policy_mode(async_client, mode: str) -> None:
    response = await async_client.post(
        "/api/v1/enforcement/policies",
        json={
            "terraform_mode": mode,
            "k8s_admission_mode": mode,
            "require_approval_for_prod": False,
            "require_approval_for_nonprod": False,
            "auto_approve_below_monthly_usd": "0",
            "hard_deny_above_monthly_usd": "2500",
            "default_ttl_seconds": 1200,
        },
    )
    assert response.status_code == 200


async def _create_pending_approval_via_api(
    async_client,
    *,
    idempotency_key: str,
    environment: str = "nonprod",
    require_approval_for_prod: bool = False,
    require_approval_for_nonprod: bool = True,
) -> dict:
    policy = await async_client.post(
        "/api/v1/enforcement/policies",
        json={
            "terraform_mode": "soft",
            "k8s_admission_mode": "soft",
            "require_approval_for_prod": require_approval_for_prod,
            "require_approval_for_nonprod": require_approval_for_nonprod,
            "auto_approve_below_monthly_usd": "0",
            "hard_deny_above_monthly_usd": "2500",
            "default_ttl_seconds": 1200,
        },
    )
    assert policy.status_code == 200

    budget = await async_client.post(
        "/api/v1/enforcement/budgets",
        json={
            "scope_key": "default",
            "monthly_limit_usd": "1000",
            "active": True,
        },
    )
    assert budget.status_code == 200

    gate = await async_client.post(
        "/api/v1/enforcement/gate/terraform",
        json={
            "project_id": "default",
            "environment": environment,
            "action": "terraform.apply",
            "resource_reference": "module.app.aws_instance.web",
            "estimated_monthly_delta_usd": "75",
            "estimated_hourly_delta_usd": "0.11",
            "metadata": {"resource_type": "aws_instance"},
            "idempotency_key": idempotency_key,
        },
    )
    assert gate.status_code == 200
    payload = gate.json()
    assert payload["decision"] == "REQUIRE_APPROVAL"
    return payload


async def _seed_member_scim_prod_permission(db, tenant_id, member_id, *, scim_enabled: bool) -> None:
    user = User(
        id=member_id,
        tenant_id=tenant_id,
        email=f"{member_id.hex[:12]}@example.com",
        role=UserRole.MEMBER.value,
        persona="engineering",
        is_active=True,
    )
    db.add(user)

    settings = TenantIdentitySettings(
        tenant_id=tenant_id,
        scim_enabled=scim_enabled,
        scim_group_mappings=[
            {
                "group": "finops-approvers",
                "permissions": [APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD],
            }
        ],
    )
    db.add(settings)
    await db.flush()

    group = ScimGroup(
        tenant_id=tenant_id,
        display_name="finops-approvers",
        display_name_norm="finops-approvers",
        external_id="finops-approvers",
        external_id_norm="finops-approvers",
    )
    db.add(group)
    await db.flush()

    db.add(
        ScimGroupMember(
            tenant_id=tenant_id,
            group_id=group.id,
            user_id=member_id,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_gate_terraform_uses_idempotency_key(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        payload = {
            "project_id": "default",
            "environment": "nonprod",
            "action": "terraform.apply",
            "resource_reference": "module.vpc.aws_vpc.main",
            "estimated_monthly_delta_usd": "15.25",
            "estimated_hourly_delta_usd": "0.02",
            "metadata": {"resource_type": "aws_vpc"},
        }
        headers = {"Idempotency-Key": "api-idem-terraform-1"}

        first = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json=payload,
            headers=headers,
        )
        second = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json=payload,
            headers=headers,
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["decision_id"] == second.json()["decision_id"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_policy_budget_and_credit_endpoints(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        get_policy = await async_client.get("/api/v1/enforcement/policies")
        assert get_policy.status_code == 200
        assert get_policy.json()["terraform_mode"] in {"shadow", "soft", "hard"}

        update_policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "hard",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": True,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert update_policy.status_code == 200
        assert update_policy.json()["terraform_mode"] == "hard"
        assert update_policy.json()["require_approval_for_nonprod"] is True

        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "2000",
                "active": True,
            },
        )
        assert budget.status_code == 200
        assert budget.json()["scope_key"] == "default"

        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        credit = await async_client.post(
            "/api/v1/enforcement/credits",
            json={
                "scope_key": "default",
                "total_amount_usd": "150",
                "expires_at": expires_at,
                "reason": "pilot credits",
            },
        )
        assert credit.status_code == 200
        assert credit.json()["remaining_amount_usd"] == "150.0000"
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_approval_flow_nonprod_can_be_approved_by_admin(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": True,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert policy.status_code == 200

        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.app.aws_instance.web",
                "estimated_monthly_delta_usd": "75",
                "estimated_hourly_delta_usd": "0.11",
                "metadata": {"resource_type": "aws_instance"},
                "idempotency_key": "api-approval-nonprod-1",
            },
        )
        assert gate.status_code == 200
        gate_payload = gate.json()
        assert gate_payload["decision"] == "REQUIRE_APPROVAL"
        assert gate_payload["approval_request_id"] is not None

        approve = await async_client.post(
            f"/api/v1/enforcement/approvals/{gate_payload['approval_request_id']}/approve",
            json={"notes": "approved by nonprod approver"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"
        assert isinstance(approve.json()["approval_token"], str)
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_approval_flow_prod_rejects_admin_without_prod_permission(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": False,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert policy.status_code == 200

        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "prod",
                "action": "terraform.apply",
                "resource_reference": "module.db.aws_db_instance.main",
                "estimated_monthly_delta_usd": "100",
                "estimated_hourly_delta_usd": "0.14",
                "metadata": {"resource_type": "aws_db_instance"},
                "idempotency_key": "api-approval-prod-1",
            },
        )
        assert gate.status_code == 200
        gate_payload = gate.json()
        assert gate_payload["decision"] == "REQUIRE_APPROVAL"
        assert gate_payload["approval_request_id"] is not None

        approve = await async_client.post(
            f"/api/v1/enforcement/approvals/{gate_payload['approval_request_id']}/approve",
            json={"notes": "attempting prod approval"},
        )
        assert approve.status_code == 403
        response_body = str(approve.json()).lower()
        assert "insufficient approval permission" in response_body
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_approval_flow_prod_allows_member_with_scim_permission(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": False,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert policy.status_code == 200

        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "prod",
                "action": "terraform.apply",
                "resource_reference": "module.db.aws_db_instance.main",
                "estimated_monthly_delta_usd": "100",
                "estimated_hourly_delta_usd": "0.14",
                "metadata": {"resource_type": "aws_db_instance"},
                "idempotency_key": "api-member-scim-prod-1",
            },
        )
        assert gate.status_code == 200
        approval_id = gate.json()["approval_request_id"]
        assert approval_id is not None

        member_id = uuid4()
        await _seed_member_scim_prod_permission(
            db,
            tenant.id,
            member_id,
            scim_enabled=True,
        )
        member_user = CurrentUser(
            id=member_id,
            email="member@enforcement.local",
            tenant_id=tenant.id,
            role=UserRole.MEMBER,
        )
        _override_user(async_client, member_user)

        approve = await async_client.post(
            f"/api/v1/enforcement/approvals/{approval_id}/approve",
            json={"notes": "approved by scim member"},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"
        assert isinstance(approve.json()["approval_token"], str)
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_approval_flow_prod_denies_member_when_scim_disabled(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": False,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert policy.status_code == 200

        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "prod",
                "action": "terraform.apply",
                "resource_reference": "module.db.aws_db_instance.main",
                "estimated_monthly_delta_usd": "100",
                "estimated_hourly_delta_usd": "0.14",
                "metadata": {"resource_type": "aws_db_instance"},
                "idempotency_key": "api-member-scim-disabled-prod-1",
            },
        )
        assert gate.status_code == 200
        approval_id = gate.json()["approval_request_id"]
        assert approval_id is not None

        member_id = uuid4()
        await _seed_member_scim_prod_permission(
            db,
            tenant.id,
            member_id,
            scim_enabled=False,
        )
        member_user = CurrentUser(
            id=member_id,
            email="member@enforcement.local",
            tenant_id=tenant.id,
            role=UserRole.MEMBER,
        )
        _override_user(async_client, member_user)

        approve = await async_client.post(
            f"/api/v1/enforcement/approvals/{approval_id}/approve",
            json={"notes": "attempt with disabled scim"},
        )
        assert approve.status_code == 403
        assert "insufficient approval permission" in str(approve.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_consume_approval_token_endpoint_rejects_replay_and_tamper(
    async_client, db
) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    try:
        token, _, _ = await _issue_approved_token_via_api(async_client)

        consume = await async_client.post(
            "/api/v1/enforcement/approvals/consume",
            json={"approval_token": token},
        )
        assert consume.status_code == 200
        consume_payload = consume.json()
        assert consume_payload["status"] == "consumed"
        assert consume_payload["request_fingerprint"]

        replay = await async_client.post(
            "/api/v1/enforcement/approvals/consume",
            json={"approval_token": token},
        )
        assert replay.status_code == 409
        assert "replay" in str(replay.json()).lower()

        header, payload, signature = token.split(".")
        decoded_payload = json.loads(base64.urlsafe_b64decode(payload + "==").decode())
        decoded_payload["resource_reference"] = "module.hijack.aws_iam_role.admin"
        tampered_payload = (
            base64.urlsafe_b64encode(json.dumps(decoded_payload).encode())
            .decode()
            .rstrip("=")
        )
        tampered_token = f"{header}.{tampered_payload}.{signature}"

        tampered = await async_client.post(
            "/api/v1/enforcement/approvals/consume",
            json={"approval_token": tampered_token},
        )
        assert tampered.status_code == 401
        assert "invalid approval token" in str(tampered.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_request_rejects_unknown_fields(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        response = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.vpc.aws_vpc.main",
                "estimated_monthly_delta_usd": "10",
                "estimated_hourly_delta_usd": "0.01",
                "metadata": {"resource_type": "aws_vpc"},
                "unexpected_field": "must_fail",
            },
        )
        assert response.status_code == 422
        assert "extra" in str(response.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "trigger", "expected_decision", "expected_mode_reason"),
    [
        ("shadow", "timeout", "ALLOW", "shadow_mode_fail_open"),
        ("soft", "timeout", "REQUIRE_APPROVAL", "soft_mode_fail_safe_escalation"),
        ("hard", "timeout", "DENY", "hard_mode_fail_closed"),
        ("shadow", "error", "ALLOW", "shadow_mode_fail_open"),
        ("soft", "error", "REQUIRE_APPROVAL", "soft_mode_fail_safe_escalation"),
        ("hard", "error", "DENY", "hard_mode_fail_closed"),
    ],
)
async def test_gate_failsafe_timeout_and_error_modes(
    async_client,
    db,
    mode: str,
    trigger: str,
    expected_decision: str,
    expected_mode_reason: str,
) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    try:
        await _set_terraform_policy_mode(async_client, mode)

        payload = {
            "project_id": "default",
            "environment": "prod",
            "action": "terraform.apply",
            "resource_reference": "module.eks.aws_eks_cluster.main",
            "estimated_monthly_delta_usd": "100",
            "estimated_hourly_delta_usd": "0.10",
            "metadata": {"resource_type": "aws_eks_cluster"},
            "idempotency_key": f"api-failsafe-{mode}-{trigger}",
        }

        async def _slow_gate(*args, **kwargs):
            _ = args, kwargs
            await asyncio.sleep(0.05)

        async def _error_gate(*args, **kwargs):
            _ = args, kwargs
            raise RuntimeError("simulated outage")

        with (
            patch(
                "app.modules.enforcement.api.v1.enforcement._gate_timeout_seconds",
                return_value=0.01 if trigger == "timeout" else 1.0,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.EnforcementService.evaluate_gate",
                side_effect=_slow_gate if trigger == "timeout" else _error_gate,
            ),
        ):
            response = await async_client.post(
                "/api/v1/enforcement/gate/terraform",
                json=payload,
            )

        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == expected_decision
        reasons = body["reason_codes"]
        assert expected_mode_reason in reasons
        if trigger == "timeout":
            assert "gate_timeout" in reasons
        else:
            assert "gate_evaluation_error" in reasons

        if expected_decision == "REQUIRE_APPROVAL":
            assert body["approval_request_id"] is not None
        else:
            assert body["approval_request_id"] is None
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_timeout_failsafe_remains_idempotent(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    try:
        await _set_terraform_policy_mode(async_client, "hard")

        payload = {
            "project_id": "default",
            "environment": "prod",
            "action": "terraform.apply",
            "resource_reference": "module.rds.aws_db_instance.main",
            "estimated_monthly_delta_usd": "80",
            "estimated_hourly_delta_usd": "0.09",
            "metadata": {"resource_type": "aws_db_instance"},
            "idempotency_key": "api-timeout-idempotent-1",
        }

        async def _slow_gate(*args, **kwargs):
            _ = args, kwargs
            await asyncio.sleep(0.05)

        with (
            patch(
                "app.modules.enforcement.api.v1.enforcement._gate_timeout_seconds",
                return_value=0.01,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.EnforcementService.evaluate_gate",
                side_effect=_slow_gate,
            ),
        ):
            first = await async_client.post(
                "/api/v1/enforcement/gate/terraform",
                json=payload,
            )
            second = await async_client.post(
                "/api/v1/enforcement/gate/terraform",
                json=payload,
            )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["decision"] == "DENY"
        assert first.json()["decision_id"] == second.json()["decision_id"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_metrics_emitted_for_normal_decision(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    decisions_counter = _FakeCounter()
    reasons_counter = _FakeCounter()
    failures_counter = _FakeCounter()
    latency_hist = _FakeHistogram()

    try:
        with (
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_DECISIONS_TOTAL",
                decisions_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_DECISION_REASONS_TOTAL",
                reasons_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_FAILURES_TOTAL",
                failures_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_LATENCY_SECONDS",
                latency_hist,
            ),
        ):
            response = await async_client.post(
                "/api/v1/enforcement/gate/terraform",
                json={
                    "project_id": "default",
                    "environment": "nonprod",
                    "action": "terraform.apply",
                    "resource_reference": "module.ec2.aws_instance.app",
                    "estimated_monthly_delta_usd": "10",
                    "estimated_hourly_delta_usd": "0.01",
                    "metadata": {"resource_type": "aws_instance"},
                    "idempotency_key": "api-metrics-normal-1",
                },
            )

        assert response.status_code == 200
        assert len(decisions_counter.calls) >= 1
        assert decisions_counter.calls[0][0]["source"] == "terraform"
        assert decisions_counter.calls[0][0]["path"] == "normal"
        assert len(latency_hist.calls) >= 1
        assert latency_hist.calls[0][0]["source"] == "terraform"
        assert latency_hist.calls[0][0]["path"] == "normal"
        assert failures_counter.calls == []
        assert len(reasons_counter.calls) >= 1
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_metrics_emitted_for_timeout_failsafe(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    decisions_counter = _FakeCounter()
    reasons_counter = _FakeCounter()
    failures_counter = _FakeCounter()
    latency_hist = _FakeHistogram()

    async def _slow_gate(*args, **kwargs):
        _ = args, kwargs
        await asyncio.sleep(0.05)

    try:
        await _set_terraform_policy_mode(async_client, "hard")
        with (
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_DECISIONS_TOTAL",
                decisions_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_DECISION_REASONS_TOTAL",
                reasons_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_FAILURES_TOTAL",
                failures_counter,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.ENFORCEMENT_GATE_LATENCY_SECONDS",
                latency_hist,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement._gate_timeout_seconds",
                return_value=0.01,
            ),
            patch(
                "app.modules.enforcement.api.v1.enforcement.EnforcementService.evaluate_gate",
                side_effect=_slow_gate,
            ),
        ):
            response = await async_client.post(
                "/api/v1/enforcement/gate/terraform",
                json={
                    "project_id": "default",
                    "environment": "prod",
                    "action": "terraform.apply",
                    "resource_reference": "module.eks.aws_eks_cluster.main",
                    "estimated_monthly_delta_usd": "100",
                    "estimated_hourly_delta_usd": "0.10",
                    "metadata": {"resource_type": "aws_eks_cluster"},
                    "idempotency_key": "api-metrics-timeout-1",
                },
            )

        assert response.status_code == 200
        assert len(failures_counter.calls) == 1
        assert failures_counter.calls[0][0]["source"] == "terraform"
        assert failures_counter.calls[0][0]["failure_type"] == "timeout"
        assert len(decisions_counter.calls) >= 1
        assert decisions_counter.calls[0][0]["path"] == "failsafe"
        assert len(latency_hist.calls) >= 1
        assert latency_hist.calls[0][0]["path"] == "failsafe"
        assert any(
            call[0]["reason"] == "gate_timeout" for call in reasons_counter.calls
        )
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_reservation_endpoint_admin(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        gate_payload = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-reconcile-reservation-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        reconcile = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "monthly close",
            },
        )
        assert reconcile.status_code == 200
        body = reconcile.json()
        assert body["decision_id"] == decision_id
        assert body["status"] == "overage"
        assert body["released_reserved_usd"] == "75.0000"
        assert body["drift_usd"] == "5.0000"
        assert body["reservation_active"] is False

        second = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            json={
                "actual_monthly_delta_usd": "80",
            },
        )
        assert second.status_code == 409

        active = await async_client.get("/api/v1/enforcement/reservations/active")
        assert active.status_code == 200
        ids = {item["decision_id"] for item in active.json()}
        assert decision_id not in ids
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_overdue_endpoint_releases_stale_reservations(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        gate_payload = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-reconcile-overdue-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]
        decision = (
            await db.execute(
                select(EnforcementDecision).where(
                    EnforcementDecision.id == UUID(decision_id)
                )
            )
        ).scalar_one()
        decision.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db.commit()

        reconcile = await async_client.post(
            "/api/v1/enforcement/reservations/reconcile-overdue",
            json={"older_than_seconds": 3600, "limit": 200},
        )
        assert reconcile.status_code == 200
        body = reconcile.json()
        assert body["released_count"] == 1
        assert body["total_released_usd"] == "75.0000"
        assert decision_id in body["decision_ids"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_reservation_endpoint_forbids_member(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        gate_payload = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-reconcile-member-denied-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        member_user = CurrentUser(
            id=uuid4(),
            email="member@enforcement.local",
            tenant_id=tenant.id,
            role=UserRole.MEMBER,
        )
        _override_user(async_client, member_user)

        reconcile = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            json={"actual_monthly_delta_usd": "80"},
        )
        assert reconcile.status_code == 403
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconciliation_exceptions_endpoint_returns_drift_only(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        drift_payload = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-reconcile-exception-drift-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        matched_payload = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-reconcile-exception-matched-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )

        drift_id = drift_payload["decision_id"]
        matched_id = matched_payload["decision_id"]

        drift_reconcile = await async_client.post(
            f"/api/v1/enforcement/reservations/{drift_id}/reconcile",
            json={"actual_monthly_delta_usd": "80"},
        )
        assert drift_reconcile.status_code == 200

        matched_reconcile = await async_client.post(
            f"/api/v1/enforcement/reservations/{matched_id}/reconcile",
            json={"actual_monthly_delta_usd": "75"},
        )
        assert matched_reconcile.status_code == 200

        exceptions = await async_client.get(
            "/api/v1/enforcement/reservations/reconciliation-exceptions?limit=50"
        )
        assert exceptions.status_code == 200
        body = exceptions.json()
        ids = {item["decision_id"] for item in body}

        assert drift_id in ids
        assert matched_id not in ids
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconciliation_exceptions_endpoint_forbids_member(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    member_user = CurrentUser(
        id=uuid4(),
        email="member@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )
    _override_user(async_client, member_user)

    try:
        response = await async_client.get(
            "/api/v1/enforcement/reservations/reconciliation-exceptions"
        )
        assert response.status_code == 403
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_enforcement_export_parity_and_archive_endpoints(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        first = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-export-bundle-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        second = await _create_pending_approval_via_api(
            async_client,
            idempotency_key="api-export-bundle-2",
            environment="prod",
            require_approval_for_prod=True,
            require_approval_for_nonprod=True,
        )
        assert first["approval_request_id"] is not None
        assert second["approval_request_id"] is not None

        parity = await async_client.get("/api/v1/enforcement/exports/parity")
        assert parity.status_code == 200
        parity_payload = parity.json()
        assert parity_payload["parity_ok"] is True
        assert parity_payload["decision_count_db"] == 2
        assert parity_payload["decision_count_exported"] == 2
        assert parity_payload["approval_count_db"] == 2
        assert parity_payload["approval_count_exported"] == 2
        assert len(parity_payload["decisions_sha256"]) == 64
        assert len(parity_payload["approvals_sha256"]) == 64

        archive = await async_client.get("/api/v1/enforcement/exports/archive")
        assert archive.status_code == 200
        assert archive.headers["content-type"].startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            names = set(bundle.namelist())
            assert "manifest.json" in names
            assert "decisions.csv" in names
            assert "approvals.csv" in names

            manifest_payload = json.loads(bundle.read("manifest.json").decode("utf-8"))
            assert manifest_payload["parity_ok"] is True
            assert manifest_payload["decision_count_db"] == 2
            assert manifest_payload["decision_count_exported"] == 2
            assert manifest_payload["approval_count_db"] == 2
            assert manifest_payload["approval_count_exported"] == 2
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_enforcement_export_endpoints_forbid_member(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    member_user = CurrentUser(
        id=uuid4(),
        email="member@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )
    _override_user(async_client, member_user)

    try:
        parity = await async_client.get("/api/v1/enforcement/exports/parity")
        archive = await async_client.get("/api/v1/enforcement/exports/archive")
        assert parity.status_code == 403
        assert archive.status_code == 403
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_decision_ledger_endpoint_admin(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.vpc.aws_vpc.main",
                "estimated_monthly_delta_usd": "20",
                "estimated_hourly_delta_usd": "0.03",
                "metadata": {"resource_type": "aws_vpc"},
                "idempotency_key": "api-ledger-1",
            },
        )
        assert gate.status_code == 200
        decision_id = gate.json()["decision_id"]

        ledger = await async_client.get("/api/v1/enforcement/ledger?limit=50")
        assert ledger.status_code == 200
        payload = ledger.json()
        assert len(payload) >= 1
        first = payload[0]
        assert first["decision_id"] == decision_id
        assert first["source"] == "terraform"
        assert len(first["request_payload_sha256"]) == 64
        assert len(first["response_payload_sha256"]) == 64
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_decision_ledger_endpoint_forbids_member(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    member_user = CurrentUser(
        id=uuid4(),
        email="member@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
    )
    _override_user(async_client, member_user)

    try:
        response = await async_client.get("/api/v1/enforcement/ledger")
        assert response.status_code == 403
    finally:
        _clear_user_override(async_client)
