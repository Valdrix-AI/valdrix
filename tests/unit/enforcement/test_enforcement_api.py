from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4
import zipfile

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.models.enforcement import EnforcementDecision
from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import User
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.models.tenant import Tenant, UserRole
from app.modules.enforcement.api.v1 import enforcement as enforcement_api
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


class _FakeGauge:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._last_labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeGauge":
        self._last_labels = dict(labels)
        return self

    def set(self, amount: float) -> None:
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


def test_enforcement_global_gate_limit_uses_configured_cap() -> None:
    with patch.object(
        enforcement_api,
        "get_settings",
        return_value=SimpleNamespace(
            ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED=True,
            ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP=321,
        ),
    ):
        assert enforcement_api._enforcement_global_gate_limit(SimpleNamespace()) == "321/minute"


def test_enforcement_global_gate_limit_fallback_when_disabled() -> None:
    with patch.object(
        enforcement_api,
        "get_settings",
        return_value=SimpleNamespace(
            ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED=False,
            ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP=1,
        ),
    ):
        assert (
            enforcement_api._enforcement_global_gate_limit(SimpleNamespace())
            == "1000000/minute"
        )


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
            "enforce_prod_requester_reviewer_separation": False,
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
        assert first.json()["approval_token"] is None
        assert first.json()["approval_token_contract"] == "approval_flow_only"
        assert isinstance(first.json().get("computed_context"), dict)
        assert "forecast_eom_usd" in first.json()["computed_context"]
        assert "burn_rate_daily_usd" in first.json()["computed_context"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_terraform_preflight_contract_and_retry_binding(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "platform",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        payload = {
            "run_id": "run-1001",
            "stage": "pre_plan",
            "workspace_id": "ws-01",
            "workspace_name": "platform-prod",
            "project_id": "platform",
            "environment": "nonprod",
            "action": "terraform.apply",
            "resource_reference": "module.vpc.aws_vpc.main",
            "estimated_monthly_delta_usd": "20",
            "estimated_hourly_delta_usd": "0.03",
            "metadata": {"resource_type": "aws_vpc"},
            "idempotency_key": "api-preflight-idempotency-1",
        }

        first = await async_client.post(
            "/api/v1/enforcement/gate/terraform/preflight",
            json=payload,
        )
        assert first.status_code == 200
        first_payload = first.json()
        assert first_payload["run_id"] == "run-1001"
        assert first_payload["stage"] == "pre_plan"
        assert first_payload["approval_token_contract"] == "approval_flow_only"
        assert first_payload["continuation"]["approval_consume_endpoint"] == (
            "/api/v1/enforcement/approvals/consume"
        )
        binding = first_payload["continuation"]["binding"]
        assert binding["expected_source"] == "terraform"
        assert binding["expected_project_id"] == "platform"
        assert binding["expected_request_fingerprint"] == first_payload["request_fingerprint"]

        retry_payload = {
            **payload,
            "expected_request_fingerprint": first_payload["request_fingerprint"],
        }
        second = await async_client.post(
            "/api/v1/enforcement/gate/terraform/preflight",
            json=retry_payload,
        )
        assert second.status_code == 200
        second_payload = second.json()
        assert first_payload["decision_id"] == second_payload["decision_id"]
        assert first_payload["request_fingerprint"] == second_payload["request_fingerprint"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_terraform_preflight_rejects_retry_fingerprint_mismatch(
    async_client, db
) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "platform",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        base_payload = {
            "run_id": "run-2001",
            "stage": "pre_apply",
            "project_id": "platform",
            "environment": "nonprod",
            "action": "terraform.apply",
            "resource_reference": "module.eks.aws_eks_cluster.main",
            "estimated_monthly_delta_usd": "60",
            "estimated_hourly_delta_usd": "0.08",
            "metadata": {"resource_type": "aws_eks_cluster"},
            "idempotency_key": "api-preflight-mismatch-1",
        }
        first = await async_client.post(
            "/api/v1/enforcement/gate/terraform/preflight",
            json=base_payload,
        )
        assert first.status_code == 200
        expected_fingerprint = first.json()["request_fingerprint"]

        mismatch = await async_client.post(
            "/api/v1/enforcement/gate/terraform/preflight",
            json={
                **base_payload,
                "estimated_monthly_delta_usd": "75",
                "expected_request_fingerprint": expected_fingerprint,
            },
        )
        assert mismatch.status_code == 409
        assert "fingerprint mismatch" in str(mismatch.json()).lower()

        decision_count = (
            await db.execute(
                select(func.count())
                .select_from(EnforcementDecision)
                .where(EnforcementDecision.tenant_id == tenant.id)
                .where(EnforcementDecision.idempotency_key == "api-preflight-mismatch-1")
            )
        ).scalar_one()
        assert int(decision_count or 0) == 1
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_terraform_preflight_approval_continuation_end_to_end(
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
        policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": False,
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
                "scope_key": "platform",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        preflight = await async_client.post(
            "/api/v1/enforcement/gate/terraform/preflight",
            json={
                "run_id": "run-3001",
                "stage": "pre_apply",
                "project_id": "platform",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.db.aws_db_instance.main",
                "estimated_monthly_delta_usd": "100",
                "estimated_hourly_delta_usd": "0.14",
                "metadata": {"resource_type": "aws_db_instance"},
                "idempotency_key": "api-preflight-approval-1",
            },
        )
        assert preflight.status_code == 200
        preflight_payload = preflight.json()
        assert preflight_payload["decision"] == "REQUIRE_APPROVAL"
        approval_request_id = preflight_payload["approval_request_id"]
        assert approval_request_id is not None

        approve = await async_client.post(
            f"/api/v1/enforcement/approvals/{approval_request_id}/approve",
            json={"notes": "approved via preflight path"},
        )
        assert approve.status_code == 200
        approval_token = approve.json()["approval_token"]
        assert isinstance(approval_token, str) and approval_token

        binding = preflight_payload["continuation"]["binding"]
        consume = await async_client.post(
            "/api/v1/enforcement/approvals/consume",
            json={
                "approval_token": approval_token,
                "expected_source": binding["expected_source"],
                "expected_project_id": binding["expected_project_id"],
                "expected_environment": binding["expected_environment"],
                "expected_request_fingerprint": binding["expected_request_fingerprint"],
                "expected_resource_reference": binding["expected_resource_reference"],
            },
        )
        assert consume.status_code == 200
        consume_payload = consume.json()
        assert consume_payload["status"] == "consumed"
        assert consume_payload["decision_id"] == preflight_payload["decision_id"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_k8s_admission_review_contract_allow(async_client, db) -> None:
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
            "/api/v1/enforcement/gate/k8s/admission/review",
            json={
                "apiVersion": "admission.k8s.io/v1",
                "kind": "AdmissionReview",
                "request": {
                    "uid": "admission-uid-1",
                    "kind": {"group": "apps", "version": "v1", "kind": "Deployment"},
                    "resource": {
                        "group": "apps",
                        "version": "v1",
                        "resource": "deployments",
                    },
                    "name": "web",
                    "namespace": "apps",
                    "operation": "CREATE",
                    "userInfo": {"username": "system:serviceaccount:apps:deployer"},
                    "object": {
                        "metadata": {
                            "labels": {
                                "valdrics.io/project-id": "platform",
                                "valdrics.io/environment": "nonprod",
                            }
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["apiVersion"] == "admission.k8s.io/v1"
        assert payload["kind"] == "AdmissionReview"
        assert payload["response"]["uid"] == "admission-uid-1"
        assert payload["response"]["allowed"] is True
        assert payload["response"]["auditAnnotations"]["valdrics.io/decision-id"]
        assert payload["response"]["auditAnnotations"]["valdrics.io/request-fingerprint"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_k8s_admission_review_uses_annotation_cost_inputs_for_deny(
    async_client, db
) -> None:
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
                "k8s_admission_mode": "hard",
                "require_approval_for_prod": False,
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
                "scope_key": "payments",
                "monthly_limit_usd": "5",
                "active": True,
            },
        )
        assert budget.status_code == 200

        response = await async_client.post(
            "/api/v1/enforcement/gate/k8s/admission/review",
            json={
                "apiVersion": "admission.k8s.io/v1",
                "kind": "AdmissionReview",
                "request": {
                    "uid": "admission-uid-2",
                    "kind": {"group": "apps", "version": "v1", "kind": "Deployment"},
                    "resource": {
                        "group": "apps",
                        "version": "v1",
                        "resource": "deployments",
                    },
                    "name": "payments-api",
                    "namespace": "payments",
                    "operation": "CREATE",
                    "object": {
                        "metadata": {
                            "annotations": {
                                "valdrics.io/project-id": "payments",
                                "valdrics.io/environment": "prod",
                                "valdrics.io/estimated-monthly-delta-usd": "50",
                                "valdrics.io/estimated-hourly-delta-usd": "0.07",
                            }
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["response"]["allowed"] is False
        assert payload["response"]["status"]["code"] == 403
        assert "decision=DENY" in payload["response"]["status"]["message"]
        assert (
            payload["response"]["auditAnnotations"]["valdrics.io/decision"] == "DENY"
        )
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_k8s_admission_review_rejects_invalid_cost_annotation(
    async_client, db
) -> None:
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
            "/api/v1/enforcement/gate/k8s/admission/review",
            json={
                "apiVersion": "admission.k8s.io/v1",
                "kind": "AdmissionReview",
                "request": {
                    "uid": "admission-uid-invalid",
                    "kind": {"group": "apps", "version": "v1", "kind": "Deployment"},
                    "resource": {
                        "group": "apps",
                        "version": "v1",
                        "resource": "deployments",
                    },
                    "name": "api",
                    "namespace": "apps",
                    "operation": "CREATE",
                    "object": {
                        "metadata": {
                            "annotations": {
                                "valdrics.io/estimated-monthly-delta-usd": "not-a-number",
                            }
                        }
                    },
                },
            },
        )
        assert response.status_code == 422
        assert "invalid admission annotation" in str(response.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_cloud_event_uses_event_id_idempotency_and_contract(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        payload = {
            "cloud_event": {
                "specversion": "1.0",
                "id": "evt-1001",
                "source": "aws.ec2",
                "type": "aws.ec2.instance.created",
                "subject": "i-0123456789abcdef0",
                "time": "2026-02-25T11:20:00Z",
                "data": {"instanceType": "m7i.large", "region": "us-east-1"},
            },
            "project_id": "default",
            "environment": "nonprod",
            "action": "cloud_event.observe",
            "estimated_monthly_delta_usd": "12",
            "estimated_hourly_delta_usd": "0.02",
        }

        first = await async_client.post(
            "/api/v1/enforcement/gate/cloud-event",
            json=payload,
        )
        second = await async_client.post(
            "/api/v1/enforcement/gate/cloud-event",
            json=payload,
        )
        assert first.status_code == 200
        assert second.status_code == 200
        first_payload = first.json()
        second_payload = second.json()
        assert first_payload["decision_id"] == second_payload["decision_id"]
        assert first_payload["request_fingerprint"] == second_payload["request_fingerprint"]
        assert first_payload["approval_token"] is None
        assert first_payload["approval_token_contract"] == "approval_flow_only"
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_cloud_event_rejects_retry_fingerprint_mismatch(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1000",
                "active": True,
            },
        )
        assert budget.status_code == 200

        base_payload = {
            "cloud_event": {
                "specversion": "1.0",
                "id": "evt-2001",
                "source": "aws.ec2",
                "type": "aws.ec2.instance.modified",
                "subject": "i-0abcdef0123456789",
                "data": {"instanceType": "m7i.2xlarge"},
            },
            "project_id": "default",
            "environment": "nonprod",
            "action": "cloud_event.observe",
            "estimated_monthly_delta_usd": "30",
            "estimated_hourly_delta_usd": "0.04",
            "idempotency_key": "api-cloud-event-fp-1",
        }
        first = await async_client.post(
            "/api/v1/enforcement/gate/cloud-event",
            json=base_payload,
        )
        assert first.status_code == 200
        first_fingerprint = first.json()["request_fingerprint"]

        mismatch = await async_client.post(
            "/api/v1/enforcement/gate/cloud-event",
            json={
                **base_payload,
                "estimated_monthly_delta_usd": "45",
                "expected_request_fingerprint": first_fingerprint,
            },
        )
        assert mismatch.status_code == 409
        assert "fingerprint mismatch" in str(mismatch.json()).lower()

        decision_count = (
            await db.execute(
                select(func.count())
                .select_from(EnforcementDecision)
                .where(EnforcementDecision.tenant_id == tenant.id)
                .where(EnforcementDecision.idempotency_key == "api-cloud-event-fp-1")
            )
        ).scalar_one()
        assert int(decision_count or 0) == 1
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_gate_cloud_event_hard_mode_can_deny_by_budget(async_client, db) -> None:
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
                "k8s_admission_mode": "hard",
                "require_approval_for_prod": False,
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
                "scope_key": "finance",
                "monthly_limit_usd": "5",
                "active": True,
            },
        )
        assert budget.status_code == 200

        response = await async_client.post(
            "/api/v1/enforcement/gate/cloud-event",
            json={
                "cloud_event": {
                    "specversion": "1.0",
                    "id": "evt-3001",
                    "source": "aws.rds",
                    "type": "aws.rds.instance.created",
                    "subject": "db-instance-main",
                    "data": {"engine": "postgres"},
                },
                "project_id": "finance",
                "environment": "prod",
                "action": "cloud_event.observe",
                "estimated_monthly_delta_usd": "80",
                "estimated_hourly_delta_usd": "0.11",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["decision"] == "DENY"
        assert "budget_exceeded" in payload["reason_codes"]
        assert payload["approval_token_contract"] == "approval_flow_only"
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
        assert (
            get_policy.json()["policy_document_schema_version"]
            == "valdrics.enforcement.policy.v1"
        )
        assert len(get_policy.json()["policy_document_sha256"]) == 64
        assert (
            get_policy.json()["policy_document"]["schema_version"]
            == "valdrics.enforcement.policy.v1"
        )

        update_policy = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "hard",
                "terraform_mode_prod": "hard",
                "terraform_mode_nonprod": "shadow",
                "k8s_admission_mode": "soft",
                "k8s_admission_mode_prod": "hard",
                "k8s_admission_mode_nonprod": "soft",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": True,
                "plan_monthly_ceiling_usd": "1500",
                "enterprise_monthly_ceiling_usd": "2500",
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "2500",
                "default_ttl_seconds": 1200,
            },
        )
        assert update_policy.status_code == 200
        assert update_policy.json()["terraform_mode"] == "hard"
        assert update_policy.json()["terraform_mode_prod"] == "hard"
        assert update_policy.json()["terraform_mode_nonprod"] == "shadow"
        assert update_policy.json()["k8s_admission_mode_prod"] == "hard"
        assert update_policy.json()["k8s_admission_mode_nonprod"] == "soft"
        assert update_policy.json()["require_approval_for_nonprod"] is True
        assert update_policy.json()["plan_monthly_ceiling_usd"] == "1500.0000"
        assert update_policy.json()["enterprise_monthly_ceiling_usd"] == "2500.0000"
        assert (
            update_policy.json()["policy_document"]["mode_matrix"]["terraform_default"]
            == "hard"
        )
        assert (
            update_policy.json()["policy_document"]["mode_matrix"]["terraform_nonprod"]
            == "shadow"
        )

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
                "pool_type": "emergency",
                "scope_key": "default",
                "total_amount_usd": "150",
                "expires_at": expires_at,
                "reason": "pilot credits",
            },
        )
        assert credit.status_code == 200
        assert credit.json()["pool_type"] == "emergency"
        assert credit.json()["remaining_amount_usd"] == "150.0000"
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_policy_upsert_accepts_policy_document_contract(async_client, db) -> None:
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
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "soft",
                "require_approval_for_prod": False,
                "require_approval_for_nonprod": False,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "10",
                "default_ttl_seconds": 900,
                "policy_document": {
                    "schema_version": "valdrics.enforcement.policy.v1",
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
                                "allowed_reviewer_roles": ["OWNER", "ADMIN"],
                            }
                        ],
                    },
                    "entitlements": {
                        "plan_monthly_ceiling_usd": "100",
                        "enterprise_monthly_ceiling_usd": "500",
                        "auto_approve_below_monthly_usd": "5",
                        "hard_deny_above_monthly_usd": "5000",
                    },
                    "execution": {"default_ttl_seconds": 1800},
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["terraform_mode"] == "hard"
        assert payload["terraform_mode_nonprod"] == "shadow"
        assert payload["k8s_admission_mode"] == "shadow"
        assert payload["k8s_admission_mode_prod"] == "hard"
        assert payload["require_approval_for_prod"] is True
        assert payload["require_approval_for_nonprod"] is True
        assert payload["auto_approve_below_monthly_usd"] == "5.0000"
        assert payload["default_ttl_seconds"] == 1800
        assert payload["approval_routing_rules"][0]["environments"] == ["prod"]
        assert payload["approval_routing_rules"][0]["allowed_reviewer_roles"] == [
            "owner",
            "admin",
        ]
        assert payload["policy_document"]["execution"]["default_ttl_seconds"] == 1800
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
                "approval_routing_rules": [
                    {
                        "rule_id": "allow-member-prod-approver",
                        "enabled": True,
                        "environments": ["prod"],
                        "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                        "allowed_reviewer_roles": ["owner", "admin", "member"],
                        "require_requester_reviewer_separation": True,
                    }
                ],
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
                "approval_routing_rules": [
                    {
                        "rule_id": "allow-member-prod-approver",
                        "enabled": True,
                        "environments": ["prod"],
                        "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                        "allowed_reviewer_roles": ["owner", "admin", "member"],
                        "require_requester_reviewer_separation": True,
                    }
                ],
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
                "approval_routing_rules": [
                    {
                        "rule_id": "allow-member-prod-approver",
                        "enabled": True,
                        "environments": ["prod"],
                        "required_permission": APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
                        "allowed_reviewer_roles": ["owner", "admin", "member"],
                        "require_requester_reviewer_separation": True,
                    }
                ],
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
        assert consume_payload["max_hourly_delta_usd"] == "0.140000"

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
async def test_consume_approval_token_endpoint_rejects_expected_project_mismatch(
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
            json={
                "approval_token": token,
                "expected_project_id": "wrong-project",
            },
        )
        assert consume.status_code == 409
        assert "expected project mismatch" in str(consume.json()).lower()
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
@pytest.mark.parametrize(
    ("lock_code", "http_status", "expected_failure_type"),
    [
        ("gate_lock_timeout", 503, "lock_timeout"),
        ("gate_lock_contended", 409, "lock_contended"),
    ],
)
async def test_gate_lock_failures_route_to_failsafe_with_lock_reason_codes(
    async_client,
    db,
    lock_code: str,
    http_status: int,
    expected_failure_type: str,
) -> None:
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
                "app.modules.enforcement.api.v1.enforcement.EnforcementService.evaluate_gate",
                side_effect=HTTPException(
                    status_code=http_status,
                    detail={
                        "code": lock_code,
                        "lock_wait_seconds": "0.120",
                        "lock_timeout_seconds": "0.200",
                    },
                ),
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
                    "idempotency_key": f"api-lock-failsafe-{lock_code}",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["decision"] == "DENY"
        assert lock_code in payload["reason_codes"]
        assert "hard_mode_fail_closed" in payload["reason_codes"]
        assert len(failures_counter.calls) == 1
        assert failures_counter.calls[0][0]["source"] == "terraform"
        assert failures_counter.calls[0][0]["failure_type"] == expected_failure_type
        assert any(call[0]["reason"] == lock_code for call in reasons_counter.calls)
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
async def test_reconcile_reservation_endpoint_idempotent_replay_header(async_client, db) -> None:
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
            idempotency_key="api-reconcile-reservation-idem-1",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        first = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "api-reconcile-idempotency-1"},
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "monthly close idempotent",
            },
        )
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["status"] == "overage"

        replay = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "api-reconcile-idempotency-1"},
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "monthly close idempotent",
            },
        )
        assert replay.status_code == 200
        replay_body = replay.json()
        assert replay_body == first_body

        mismatch = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "api-reconcile-idempotency-1"},
            json={
                "actual_monthly_delta_usd": "81",
                "notes": "monthly close idempotent",
            },
        )
        assert mismatch.status_code == 409
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_reservation_rejects_invalid_idempotency_key_header(async_client, db) -> None:
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
            idempotency_key="api-reconcile-reservation-idem-2",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        response = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "x"},
            json={"actual_monthly_delta_usd": "80"},
        )
        assert response.status_code == 422
        body = response.json()
        assert "idempotency_key" in str(body.get("error", "")).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_reservation_endpoint_idempotent_replay_body_key(async_client, db) -> None:
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
            idempotency_key="api-reconcile-reservation-idem-3",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        first = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "body-idem",
                "idempotency_key": "api-reconcile-body-idem-1",
            },
        )
        assert first.status_code == 200
        first_body = first.json()

        replay = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "body-idem",
                "idempotency_key": "api-reconcile-body-idem-1",
            },
        )
        assert replay.status_code == 200
        assert replay.json() == first_body
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_reservation_header_idempotency_key_precedence(async_client, db) -> None:
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
            idempotency_key="api-reconcile-reservation-idem-4",
            environment="nonprod",
            require_approval_for_prod=False,
            require_approval_for_nonprod=True,
        )
        decision_id = gate_payload["decision_id"]

        first = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "api-reconcile-header-idem-1"},
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "header-precedence",
                "idempotency_key": "api-reconcile-body-shadow-a",
            },
        )
        assert first.status_code == 200
        first_body = first.json()

        replay = await async_client.post(
            f"/api/v1/enforcement/reservations/{decision_id}/reconcile",
            headers={"Idempotency-Key": "api-reconcile-header-idem-1"},
            json={
                "actual_monthly_delta_usd": "80",
                "notes": "header-precedence",
                "idempotency_key": "api-reconcile-body-shadow-b",
            },
        )
        assert replay.status_code == 200
        assert replay.json() == first_body
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
        assert len(parity_payload["policy_lineage_sha256"]) == 64
        assert parity_payload["policy_lineage_entries"] >= 1
        assert len(parity_payload["computed_context_lineage_sha256"]) == 64
        assert parity_payload["computed_context_lineage_entries"] >= 1
        assert len(parity_payload["manifest_content_sha256"]) == 64
        assert len(parity_payload["manifest_signature"]) == 64
        assert parity_payload["manifest_signature_algorithm"] == "hmac-sha256"
        assert len(parity_payload["manifest_signature_key_id"]) >= 1

        archive = await async_client.get("/api/v1/enforcement/exports/archive")
        assert archive.status_code == 200
        assert archive.headers["content-type"].startswith("application/zip")

        with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
            names = set(bundle.namelist())
            assert "manifest.json" in names
            assert "manifest.canonical.json" in names
            assert "manifest.sha256" in names
            assert "manifest.sig" in names
            assert "decisions.csv" in names
            assert "approvals.csv" in names

            manifest_payload = json.loads(bundle.read("manifest.json").decode("utf-8"))
            assert manifest_payload["parity_ok"] is True
            assert manifest_payload["decision_count_db"] == 2
            assert manifest_payload["decision_count_exported"] == 2
            assert manifest_payload["approval_count_db"] == 2
            assert manifest_payload["approval_count_exported"] == 2
            assert len(manifest_payload["policy_lineage_sha256"]) == 64
            assert isinstance(manifest_payload["policy_lineage"], list)
            assert len(manifest_payload["policy_lineage"]) >= 1
            assert len(manifest_payload["computed_context_lineage_sha256"]) == 64
            assert isinstance(manifest_payload["computed_context_lineage"], list)
            assert len(manifest_payload["computed_context_lineage"]) >= 1
            canonical_manifest = bundle.read("manifest.canonical.json").decode("utf-8")
            canonical_manifest_sha256 = hashlib.sha256(
                canonical_manifest.encode("utf-8")
            ).hexdigest()
            assert canonical_manifest_sha256 == manifest_payload["manifest_content_sha256"]
            assert manifest_payload["manifest_content_sha256"] == parity_payload["manifest_content_sha256"]
            assert bundle.read("manifest.sha256").decode("utf-8").strip() == manifest_payload["manifest_content_sha256"]
            assert bundle.read("manifest.sig").decode("utf-8").strip() == manifest_payload["manifest_signature"]
            assert manifest_payload["manifest_signature"] == parity_payload["manifest_signature"]
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
        assert first["burn_rate_daily_usd"] is not None
        assert first["forecast_eom_usd"] is not None
        assert first["risk_class"] in {"low", "medium", "high"}
        assert first["policy_document_schema_version"] == "valdrics.enforcement.policy.v1"
        assert len(first["policy_document_sha256"]) == 64
        assert first["approval_request_id"] is None
        assert first["approval_status"] is None
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


@pytest.mark.asyncio
async def test_approval_queue_create_request_and_deny_endpoints(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)
    fake_queue_backlog = _FakeGauge()

    try:
        with patch(
            "app.modules.enforcement.api.v1.approvals.ENFORCEMENT_APPROVAL_QUEUE_BACKLOG",
            fake_queue_backlog,
        ):
            gate_payload = await _create_pending_approval_via_api(
                async_client,
                idempotency_key="api-approval-queue-create-deny-1",
                environment="nonprod",
                require_approval_for_prod=False,
                require_approval_for_nonprod=True,
            )
            approval_id = gate_payload["approval_request_id"]
            decision_id = gate_payload["decision_id"]
            assert approval_id is not None

            create = await async_client.post(
                "/api/v1/enforcement/approvals/requests",
                json={"decision_id": decision_id, "notes": "queue me"},
            )
            assert create.status_code == 200
            create_payload = create.json()
            assert create_payload["approval_id"] == approval_id
            assert create_payload["status"] == "pending"

            queue = await async_client.get("/api/v1/enforcement/approvals/queue?limit=50")
            assert queue.status_code == 200
            queue_ids = {item["approval_id"] for item in queue.json()}
            assert approval_id in queue_ids
            assert fake_queue_backlog.calls
            labels, value = fake_queue_backlog.calls[-1]
            assert labels["viewer_role"] == "admin"
            assert value >= 1.0

            deny = await async_client.post(
                f"/api/v1/enforcement/approvals/{approval_id}/deny",
                json={"notes": "denied by admin"},
            )
            assert deny.status_code == 200
            deny_payload = deny.json()
            assert deny_payload["status"] == "denied"
            assert deny_payload["approval_token"] is None
            assert deny_payload["token_expires_at"] is None
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_consume_approval_token_conflict_error_paths(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.OWNER,
    )
    _override_user(async_client, owner_user)

    decision = SimpleNamespace(
        id=uuid4(),
        source=SimpleNamespace(value="terraform"),
        environment="prod",
        project_id="default",
        action="terraform.apply",
        resource_reference="module.db.aws_db_instance.main",
        request_fingerprint="fp-123",
        estimated_monthly_delta_usd="100.00",
        token_expires_at=None,
    )

    try:
        approval_missing_expiry = SimpleNamespace(
            id=uuid4(),
            approval_token_expires_at=None,
            approval_token_consumed_at=datetime.now(timezone.utc),
        )
        with patch(
            "app.modules.enforcement.api.v1.approvals.EnforcementService.consume_approval_token",
            new_callable=AsyncMock,
            return_value=(approval_missing_expiry, decision),
        ):
            missing_expiry = await async_client.post(
                "/api/v1/enforcement/approvals/consume",
                json={"approval_token": "x" * 48},
            )
        assert missing_expiry.status_code == 409
        assert "expiry is unavailable" in str(missing_expiry.json()).lower()

        approval_not_consumed = SimpleNamespace(
            id=uuid4(),
            approval_token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            approval_token_consumed_at=None,
        )
        with patch(
            "app.modules.enforcement.api.v1.approvals.EnforcementService.consume_approval_token",
            new_callable=AsyncMock,
            return_value=(approval_not_consumed, decision),
        ):
            not_consumed = await async_client.post(
                "/api/v1/enforcement/approvals/consume",
                json={"approval_token": "y" * 48},
            )
        assert not_consumed.status_code == 409
        assert "was not consumed" in str(not_consumed.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_policy_budget_credit_list_endpoints_with_member_access(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        policy_update = await async_client.post(
            "/api/v1/enforcement/policies",
            json={
                "terraform_mode": "soft",
                "k8s_admission_mode": "hard",
                "require_approval_for_prod": True,
                "require_approval_for_nonprod": True,
                "auto_approve_below_monthly_usd": "10",
                "hard_deny_above_monthly_usd": "3000",
                "default_ttl_seconds": 900,
            },
        )
        assert policy_update.status_code == 200

        budget_create = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={
                "scope_key": "default",
                "monthly_limit_usd": "1200",
                "active": True,
            },
        )
        assert budget_create.status_code == 200

        expires_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        credit_create = await async_client.post(
            "/api/v1/enforcement/credits",
            json={
                "scope_key": "default",
                "total_amount_usd": "250",
                "expires_at": expires_at,
                "reason": "integration test credit",
            },
        )
        assert credit_create.status_code == 200

        member_user = CurrentUser(
            id=uuid4(),
            email="member@enforcement.local",
            tenant_id=tenant.id,
            role=UserRole.MEMBER,
        )
        _override_user(async_client, member_user)

        policy_get = await async_client.get("/api/v1/enforcement/policies")
        budgets_get = await async_client.get("/api/v1/enforcement/budgets")
        credits_get = await async_client.get("/api/v1/enforcement/credits")

        assert policy_get.status_code == 200
        assert policy_get.json()["k8s_admission_mode"] == "hard"
        assert budgets_get.status_code == 200
        assert len(budgets_get.json()) == 1
        assert budgets_get.json()[0]["scope_key"] == "default"
        assert credits_get.status_code == 200
        assert len(credits_get.json()) == 1
        assert credits_get.json()[0]["reason"] == "integration test credit"
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_reconcile_overdue_uses_configured_default_sla(async_client, db) -> None:
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
            idempotency_key="api-reconcile-default-sla-1",
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
        decision.created_at = datetime.now(timezone.utc) - timedelta(hours=3)
        await db.commit()

        with patch(
            "app.modules.enforcement.api.v1.reservations.get_settings",
            return_value=SimpleNamespace(
                ENFORCEMENT_RESERVATION_RECONCILIATION_SLA_SECONDS=7200
            ),
        ):
            reconcile = await async_client.post(
                "/api/v1/enforcement/reservations/reconcile-overdue",
                json={"limit": 50},
            )
        assert reconcile.status_code == 200
        payload = reconcile.json()
        assert payload["released_count"] == 1
        assert payload["older_than_seconds"] == 7200
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_export_parity_validation_branches(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        bad_order = await async_client.get(
            "/api/v1/enforcement/exports/parity"
            "?start_date=2026-02-10&end_date=2026-02-01"
        )
        assert bad_order.status_code == 422
        assert "on or before end_date" in str(bad_order.json()).lower()

        too_wide = await async_client.get(
            "/api/v1/enforcement/exports/parity"
            "?start_date=2024-01-01&end_date=2026-02-01"
        )
        assert too_wide.status_code == 422
        assert "date window exceeds export limit" in str(too_wide.json()).lower()

        bad_max_rows = await async_client.get(
            "/api/v1/enforcement/exports/parity?max_rows=0"
        )
        assert bad_max_rows.status_code == 422
        assert "max_rows must be >= 1" in str(bad_max_rows.json()).lower()

        too_large_max_rows = await async_client.get(
            "/api/v1/enforcement/exports/parity?max_rows=50001"
        )
        assert too_large_max_rows.status_code == 422
        assert "max_rows must be <=" in str(too_large_max_rows.json()).lower()
    finally:
        _clear_user_override(async_client)


def test_export_limit_helper_fallback_branches() -> None:
    from app.modules.enforcement.api.v1.exports import _export_max_days, _export_max_rows

    with patch(
        "app.modules.enforcement.api.v1.exports.get_settings",
        return_value=SimpleNamespace(
            ENFORCEMENT_EXPORT_MAX_DAYS="not-an-int",
            ENFORCEMENT_EXPORT_MAX_ROWS="not-an-int",
        ),
    ):
        assert _export_max_days() == 366
        assert _export_max_rows() == 10000

    with patch(
        "app.modules.enforcement.api.v1.exports.get_settings",
        return_value=SimpleNamespace(
            ENFORCEMENT_EXPORT_MAX_DAYS=0,
            ENFORCEMENT_EXPORT_MAX_ROWS=999999,
        ),
    ):
        assert _export_max_days() == 1
        assert _export_max_rows() == 50000
