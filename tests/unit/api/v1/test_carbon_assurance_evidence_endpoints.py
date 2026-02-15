import uuid

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_carbon_assurance_evidence(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user
    from app.models.carbon_factors import CarbonFactorSet
    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from sqlalchemy import select

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-carbon@valdrix.io",
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
        payload = {"runner": "unit-test", "notes": "capture carbon assurance"}
        resp = await async_client.post(
            "/api/v1/audit/carbon/assurance/evidence", json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        snapshot = body["carbon_assurance"]["snapshot"]
        assert "methodology_version" in snapshot
        assert "factors_checksum_sha256" in snapshot
        assert body["carbon_assurance"]["factor_set_id"] is not None
        assert body["carbon_assurance"]["factor_set_status"] in {
            "active",
            "archived",
            "staged",
            "blocked",
        }

        list_resp = await async_client.get(
            "/api/v1/audit/carbon/assurance/evidence", params={"limit": 10}
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert "snapshot" in listed["items"][0]["carbon_assurance"]
        assert listed["items"][0]["carbon_assurance"]["factor_set_id"] is not None

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value,
            )
        )
        assert row is not None

        factor_set = await db.scalar(
            select(CarbonFactorSet).where(CarbonFactorSet.is_active.is_(True))
        )
        assert factor_set is not None
        assert str(factor_set.id) == body["carbon_assurance"]["factor_set_id"]
        assert snapshot["factors_checksum_sha256"] == factor_set.factors_checksum_sha256
    finally:
        app.dependency_overrides.pop(get_current_user, None)
