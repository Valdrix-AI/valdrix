import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_tenant_isolation_evidence(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier
    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from sqlalchemy import select

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-tenancy@valdrix.io",
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
        payload = {
            "runner": "scripts/verify_tenant_isolation.py",
            "checks": [
                "connections_list_is_tenant_scoped",
                "notification_settings_get_is_tenant_scoped",
            ],
            "passed": True,
            "pytest_exit_code": 0,
            "duration_seconds": 1.234,
            "git_sha": "deadbeef",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "notes": "unit-test capture",
        }

        resp = await async_client.post(
            "/api/v1/audit/tenancy/isolation/evidence", json=payload
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert body["tenant_isolation"]["passed"] is True

        list_resp = await async_client.get(
            "/api/v1/audit/tenancy/isolation/evidence", params={"limit": 10}
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert (
            listed["items"][0]["tenant_isolation"]["runner"]
            == "scripts/verify_tenant_isolation.py"
        )

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
