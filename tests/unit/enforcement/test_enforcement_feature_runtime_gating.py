from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.tenant import Tenant, UserRole
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


async def _seed_tenant(db, *, plan: PricingTier) -> Tenant:
    tenant = Tenant(
        id=uuid4(),
        name=f"enforcement-feature-gating-{plan.value}",
        plan=plan.value,
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


def _override_user(async_client, user: CurrentUser) -> None:
    async_client.app.dependency_overrides[get_current_user] = lambda: user


def _clear_user(async_client) -> None:
    async_client.app.dependency_overrides.pop(get_current_user, None)


def _error_text(response) -> str:
    payload = response.json()
    return str(
        payload.get("detail")
        or payload.get("message")
        or payload.get("error")
        or ""
    )


@pytest.mark.asyncio
async def test_gate_terraform_denies_free_tier_without_control_plane_features(
    async_client,
    db,
) -> None:
    tenant = await _seed_tenant(db, plan=PricingTier.FREE)
    user = CurrentUser(
        id=uuid4(),
        email="free-enforcement@test.local",
        tenant_id=tenant.id,
        role=UserRole.MEMBER,
        tier=PricingTier.FREE,
    )
    _override_user(async_client, user)

    try:
        response = await async_client.post(
            "/api/v1/enforcement/gate/terraform",
            json={
                "project_id": "default",
                "environment": "nonprod",
                "action": "terraform.apply",
                "resource_reference": "module.app.aws_instance.free-gate",
                "estimated_monthly_delta_usd": "10",
                "estimated_hourly_delta_usd": "0.01",
                "metadata": {"resource_type": "aws_instance"},
                "idempotency_key": "feature-gating-free-gate-1",
            },
        )
        assert response.status_code == 403
        detail = _error_text(response)
        assert "api_access" in detail
        assert "policy_configuration" in detail
    finally:
        _clear_user(async_client)


@pytest.mark.asyncio
async def test_ledger_and_policy_endpoints_enforce_feature_specific_gates(
    async_client,
    db,
) -> None:
    tenant = await _seed_tenant(db, plan=PricingTier.FREE)
    user = CurrentUser(
        id=uuid4(),
        email="free-read@test.local",
        tenant_id=tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.FREE,
    )
    _override_user(async_client, user)

    try:
        ledger_response = await async_client.get("/api/v1/enforcement/ledger?limit=10")
        assert ledger_response.status_code == 403
        assert "api_access" in _error_text(ledger_response)

        policy_response = await async_client.get("/api/v1/enforcement/policies")
        assert policy_response.status_code == 403
        assert "policy_configuration" in _error_text(policy_response)
    finally:
        _clear_user(async_client)
