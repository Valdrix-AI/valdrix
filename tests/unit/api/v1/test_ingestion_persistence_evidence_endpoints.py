import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_ingestion_persistence_evidence(
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
        email="admin-ingest@valdrics.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    # Ensure FK-safe actor_id insertion for audit logs.
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
            "runner": "scripts/benchmark_ingestion_persistence.py",
            "provider": "aws",
            "account_id": str(uuid.uuid4()),
            "records_requested": 100_000,
            "records_saved": 100_000,
            "duration_seconds": 12.34,
            "records_per_second": 8101.2,
            "services": 25,
            "regions": 5,
            "cleanup": True,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "thresholds": {"min_records_per_second": 5000.0},
            "meets_targets": True,
        }

        resp = await async_client.post(
            "/api/v1/audit/performance/ingestion/persistence/evidence",
            json=payload,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert body["benchmark"]["records_requested"] == 100_000
        assert body["benchmark"]["provider"] == "aws"

        list_resp = await async_client.get(
            "/api/v1/audit/performance/ingestion/persistence/evidence",
            params={"limit": 10},
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert listed["items"][0]["benchmark"]["provider"] == "aws"

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
