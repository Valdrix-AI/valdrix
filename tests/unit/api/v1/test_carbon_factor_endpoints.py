import uuid

import pytest


def _make_factor_payload(
    *, factor_version: str, factor_timestamp: str, default_intensity: int
) -> dict:
    from app.modules.reporting.domain.calculator import build_carbon_factor_payload

    payload = build_carbon_factor_payload()
    payload["region_carbon_intensity"] = dict(
        payload.get("region_carbon_intensity") or {}
    )
    payload["region_carbon_intensity"]["default"] = int(default_intensity)
    payload["factor_version"] = factor_version
    payload["factor_timestamp"] = factor_timestamp
    return payload


@pytest.mark.asyncio
async def test_carbon_factor_stage_activate_and_list(
    async_client, app, db, test_tenant
):
    from app.models.tenant import User
    from app.shared.core.auth import CurrentUser, get_current_user

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-carbon-factors@valdrix.io",
        tenant_id=test_tenant.id,
        role="admin",
        tier="pro",
    )
    db.add(
        User(
            id=admin_user.id,
            tenant_id=test_tenant.id,
            email=admin_user.email,
            role="admin",
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        active_resp = await async_client.get("/api/v1/carbon/factors/active")
        assert active_resp.status_code == 200
        active_body = active_resp.json()
        assert active_body["is_active"] is True
        assert active_body["status"] == "active"

        staged_payload = _make_factor_payload(
            factor_version="2026-02-14-test-stage",
            factor_timestamp="2026-02-14",
            default_intensity=420,
        )
        stage_resp = await async_client.post(
            "/api/v1/carbon/factors",
            json={"payload": staged_payload, "message": "stage from unit test"},
        )
        assert stage_resp.status_code == 200
        staged = stage_resp.json()
        assert staged["status"] == "staged"
        assert staged["is_active"] is False

        activate_resp = await async_client.post(
            f"/api/v1/carbon/factors/{staged['id']}/activate"
        )
        assert activate_resp.status_code == 200
        activated = activate_resp.json()
        assert activated["id"] == staged["id"]
        assert activated["status"] == "active"
        assert activated["is_active"] is True

        list_resp = await async_client.get("/api/v1/carbon/factors")
        assert list_resp.status_code == 200
        factor_items = list_resp.json()["items"]
        assert any(item["id"] == staged["id"] for item in factor_items)

        updates_resp = await async_client.get("/api/v1/carbon/factors/updates")
        assert updates_resp.status_code == 200
        actions = {item["action"] for item in updates_resp.json()["items"]}
        assert "staged" in actions
        assert "manual_activated" in actions
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_carbon_factor_auto_activate_latest(async_client, app, db, test_tenant):
    from app.models.tenant import User
    from app.shared.core.auth import CurrentUser, get_current_user

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-carbon-auto@valdrix.io",
        tenant_id=test_tenant.id,
        role="admin",
        tier="pro",
    )
    db.add(
        User(
            id=admin_user.id,
            tenant_id=test_tenant.id,
            email=admin_user.email,
            role="admin",
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        active_resp = await async_client.get("/api/v1/carbon/factors/active")
        assert active_resp.status_code == 200
        old_active_id = active_resp.json()["id"]

        staged_payload = _make_factor_payload(
            factor_version="2026-02-15-test-auto",
            factor_timestamp="2026-02-15",
            default_intensity=430,
        )
        stage_resp = await async_client.post(
            "/api/v1/carbon/factors",
            json={"payload": staged_payload, "message": "auto activation candidate"},
        )
        assert stage_resp.status_code == 200
        staged = stage_resp.json()

        auto_resp = await async_client.post("/api/v1/carbon/factors/auto-activate")
        assert auto_resp.status_code == 200
        auto_body = auto_resp.json()
        assert auto_body["status"] == "activated"
        assert auto_body["active_factor_set_id"] == staged["id"]

        new_active_resp = await async_client.get("/api/v1/carbon/factors/active")
        assert new_active_resp.status_code == 200
        new_active = new_active_resp.json()
        assert new_active["id"] != old_active_id
        assert new_active["id"] == staged["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
