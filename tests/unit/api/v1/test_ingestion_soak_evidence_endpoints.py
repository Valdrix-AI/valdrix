import uuid
from datetime import datetime, timezone

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_ingestion_soak_evidence(
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
        email="admin-soak@valdrix.io",
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
            "runner": "scripts/soak_ingestion_jobs.py",
            "jobs_enqueued": 5,
            "workers": 2,
            "batch_limit": 10,
            "window": {"start_date": "2026-02-01", "end_date": "2026-02-13"},
            "results": {
                "jobs_total": 5,
                "jobs_succeeded": 5,
                "jobs_failed": 0,
                "success_rate_percent": 100.0,
                "avg_duration_seconds": 12.0,
                "median_duration_seconds": 11.5,
                "p95_duration_seconds": 18.2,
                "p99_duration_seconds": 18.2,
                "min_duration_seconds": 9.5,
                "max_duration_seconds": 18.2,
                "errors_sample": [],
            },
            "runs": [
                {
                    "job_id": str(uuid.uuid4()),
                    "status": "completed",
                    "duration_seconds": 11.5,
                    "ingested_records": 5000,
                    "error": None,
                }
            ],
            "thresholds": {"max_p95_duration_seconds": 60},
            "meets_targets": True,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "notes": "unit-test",
        }

        resp = await async_client.post(
            "/api/v1/audit/performance/ingestion/soak/evidence",
            json=payload,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert body["ingestion_soak"]["jobs_enqueued"] == 5
        assert body["ingestion_soak"]["results"]["jobs_failed"] == 0

        list_resp = await async_client.get(
            "/api/v1/audit/performance/ingestion/soak/evidence",
            params={"limit": 10},
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert listed["items"][0]["ingestion_soak"]["jobs_enqueued"] == 5

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type
                == AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
