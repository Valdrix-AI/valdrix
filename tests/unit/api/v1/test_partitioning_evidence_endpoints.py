import uuid

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_partitioning_evidence(
    async_client, app, db, test_tenant
):
    from sqlalchemy import select

    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-partitioning@valdrics.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    db.add(
        User(
            id=admin_user.id,
            tenant_id=test_tenant.id,
            email=admin_user.email,
            role=UserRole.ADMIN,
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = await async_client.post(
            "/api/v1/audit/performance/partitioning/evidence"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert "partitioning" in body
        assert isinstance(body["partitioning"]["tables"], list)

        list_resp = await async_client.get(
            "/api/v1/audit/performance/partitioning/evidence",
            params={"limit": 10},
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert (
            listed["items"][0]["partitioning"]["dialect"]
            == body["partitioning"]["dialect"]
        )

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
