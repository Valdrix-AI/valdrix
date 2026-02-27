from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.models.tenant import Tenant, UserRole
from app.shared.core.auth import CurrentUser, get_current_user


async def _seed_tenant(db) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name="Enforcement Actions API Tenant",
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


async def _create_approved_decision_via_api(async_client) -> UUID:
    policy = await async_client.post(
        "/api/v1/enforcement/policies",
        json={
            "terraform_mode": "soft",
            "k8s_admission_mode": "soft",
            "require_approval_for_prod": False,
            "require_approval_for_nonprod": True,
            "auto_approve_below_monthly_usd": "0",
            "hard_deny_above_monthly_usd": "1000",
            "default_ttl_seconds": 900,
        },
    )
    assert policy.status_code == 200
    budget = await async_client.post(
        "/api/v1/enforcement/budgets",
        json={"scope_key": "default", "monthly_limit_usd": "1000", "active": True},
    )
    assert budget.status_code == 200
    gate = await async_client.post(
        "/api/v1/enforcement/gate/terraform",
        json={
            "project_id": "default",
            "environment": "nonprod",
            "action": "terraform.apply",
            "resource_reference": "module.app.aws_instance.api-actions",
            "estimated_monthly_delta_usd": "50",
            "estimated_hourly_delta_usd": "0.07",
            "metadata": {"resource_type": "aws_instance"},
            "idempotency_key": "actions-api-approved-decision-1",
        },
    )
    assert gate.status_code == 200
    gate_payload = gate.json()
    assert gate_payload["decision"] == "REQUIRE_APPROVAL"
    approval_id = gate_payload["approval_request_id"]
    assert approval_id is not None

    approve = await async_client.post(
        f"/api/v1/enforcement/approvals/{approval_id}/approve",
        json={"notes": "approve for actions api tests"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"
    return UUID(gate_payload["decision_id"])


@pytest.mark.asyncio
async def test_actions_api_lifecycle_create_lease_complete(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        decision_id = await _create_approved_decision_via_api(async_client)
        create = await async_client.post(
            "/api/v1/enforcement/actions/requests",
            json={
                "decision_id": str(decision_id),
                "action_type": "terraform.apply.execute",
                "target_reference": "module.app.aws_instance.api-actions",
                "request_payload": {"provider": "terraform"},
                "idempotency_key": "actions-api-lifecycle-1",
            },
        )
        assert create.status_code == 200
        create_payload = create.json()
        assert create_payload["status"] == "queued"
        action_id = create_payload["action_id"]

        lease = await async_client.post(
            "/api/v1/enforcement/actions/lease",
            json={"action_type": "terraform.apply.execute"},
        )
        assert lease.status_code == 200
        lease_payload = lease.json()
        assert lease_payload is not None
        assert lease_payload["action_id"] == action_id
        assert lease_payload["status"] == "running"
        assert lease_payload["attempt_count"] == 1

        complete = await async_client.post(
            f"/api/v1/enforcement/actions/requests/{action_id}/complete",
            json={"result_payload": {"provider_request_id": "tf-run-123"}},
        )
        assert complete.status_code == 200
        complete_payload = complete.json()
        assert complete_payload["status"] == "succeeded"
        assert complete_payload["result_payload"]["provider_request_id"] == "tf-run-123"

        get_action = await async_client.get(
            f"/api/v1/enforcement/actions/requests/{action_id}"
        )
        assert get_action.status_code == 200
        assert get_action.json()["status"] == "succeeded"

        listed = await async_client.get(
            "/api/v1/enforcement/actions/requests?status=succeeded&limit=50"
        )
        assert listed.status_code == 200
        assert any(item["action_id"] == action_id for item in listed.json())
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_actions_api_create_is_idempotent(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        decision_id = await _create_approved_decision_via_api(async_client)
        first = await async_client.post(
            "/api/v1/enforcement/actions/requests",
            json={
                "decision_id": str(decision_id),
                "action_type": "terraform.apply.execute",
                "target_reference": "module.app.aws_instance.api-actions",
                "request_payload": {"provider": "terraform"},
                "idempotency_key": "actions-api-idempotent-1",
            },
        )
        assert first.status_code == 200
        second = await async_client.post(
            "/api/v1/enforcement/actions/requests",
            json={
                "decision_id": str(decision_id),
                "action_type": "terraform.apply.execute",
                "target_reference": "module.app.aws_instance.api-actions",
                "request_payload": {"provider": "terraform"},
                "idempotency_key": "actions-api-idempotent-1",
            },
        )
        assert second.status_code == 200
        assert first.json()["action_id"] == second.json()["action_id"]
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_actions_api_rejects_denied_decision(async_client, db) -> None:
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
                "terraform_mode": "hard",
                "k8s_admission_mode": "hard",
                "require_approval_for_prod": False,
                "require_approval_for_nonprod": False,
                "auto_approve_below_monthly_usd": "0",
                "hard_deny_above_monthly_usd": "1000",
                "default_ttl_seconds": 900,
            },
        )
        assert policy.status_code == 200
        budget = await async_client.post(
            "/api/v1/enforcement/budgets",
            json={"scope_key": "default", "monthly_limit_usd": "10", "active": True},
        )
        assert budget.status_code == 200
        gate = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.app.aws_instance.denied-actions",
                "estimated_monthly_delta_usd": "50",
                "estimated_hourly_delta_usd": "0.07",
                "metadata": {"resource_type": "aws_instance"},
                "idempotency_key": "actions-api-denied-decision-1",
            },
        )
        assert gate.status_code == 200
        gate_payload = gate.json()
        assert gate_payload["decision"] == "DENY"

        create = await async_client.post(
            "/api/v1/enforcement/actions/requests",
            json={
                "decision_id": gate_payload["decision_id"],
                "action_type": "terraform.apply.execute",
                "target_reference": "module.app.aws_instance.denied-actions",
                "request_payload": {"provider": "terraform"},
                "idempotency_key": "actions-api-denied-1",
            },
        )
        assert create.status_code == 409
        assert "denied decision" in str(create.json()).lower()
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_actions_api_lease_returns_none_when_no_action_available(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        lease = await async_client.post(
            "/api/v1/enforcement/actions/lease",
            json={"action_type": "terraform.apply.execute"},
        )
        assert lease.status_code == 200
        assert lease.json() is None
    finally:
        _clear_user_override(async_client)


@pytest.mark.asyncio
async def test_actions_api_fail_and_cancel_endpoints(async_client, db) -> None:
    tenant = await _seed_tenant(db)
    admin_user = CurrentUser(
        id=uuid4(),
        email="admin@enforcement.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
    )
    _override_user(async_client, admin_user)

    try:
        decision_id = await _create_approved_decision_via_api(async_client)
        create = await async_client.post(
            "/api/v1/enforcement/actions/requests",
            json={
                "decision_id": str(decision_id),
                "action_type": "terraform.apply.execute",
                "target_reference": "module.app.aws_instance.api-actions-fail-cancel",
                "request_payload": {"provider": "terraform"},
                "idempotency_key": "actions-api-fail-cancel-1",
            },
        )
        assert create.status_code == 200
        action_id = create.json()["action_id"]

        lease = await async_client.post(
            "/api/v1/enforcement/actions/lease",
            json={"action_type": "terraform.apply.execute"},
        )
        assert lease.status_code == 200
        assert lease.json()["action_id"] == action_id

        fail = await async_client.post(
            f"/api/v1/enforcement/actions/requests/{action_id}/fail",
            json={
                "error_code": "provider_timeout",
                "error_message": "provider timeout",
                "retryable": True,
            },
        )
        assert fail.status_code == 200
        assert fail.json()["status"] == "queued"
        assert fail.json()["last_error_code"] == "provider_timeout"

        cancel = await async_client.post(
            f"/api/v1/enforcement/actions/requests/{action_id}/cancel",
            json={"reason": "manual operator intervention"},
        )
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"
        assert cancel.json()["last_error_code"] == "cancelled"
    finally:
        _clear_user_override(async_client)
