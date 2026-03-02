import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_capture_and_list_job_slo_evidence(async_client, app, db, test_tenant):
    from sqlalchemy import select

    from app.models.background_job import BackgroundJob, JobStatus, JobType
    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-jobs-slo@valdrics.io",
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

    now = datetime.now(timezone.utc)
    completed = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        job_type=JobType.COST_INGESTION.value,
        status=JobStatus.COMPLETED.value,
        attempts=0,
        scheduled_for=now,
        created_at=now,
        started_at=now - timedelta(seconds=30),
        completed_at=now,
        is_deleted=False,
    )
    failed = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        job_type=JobType.COST_INGESTION.value,
        status=JobStatus.FAILED.value,
        attempts=1,
        scheduled_for=now,
        created_at=now,
        started_at=now - timedelta(seconds=10),
        completed_at=now,
        error_message="boom",
        is_deleted=False,
    )
    pending = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=test_tenant.id,
        job_type=JobType.ZOMBIE_SCAN.value,
        status=JobStatus.PENDING.value,
        attempts=0,
        scheduled_for=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=5),
        is_deleted=False,
    )
    db.add_all([completed, failed, pending])
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        resp = await async_client.post(
            "/api/v1/audit/jobs/slo/evidence",
            json={"window_hours": 1, "target_success_rate_percent": 50.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "captured"
        assert body["job_slo"]["window_hours"] == 1
        assert body["job_slo"]["target_success_rate_percent"] == 50.0
        assert isinstance(body["job_slo"]["metrics"], list)
        assert body["job_slo"]["backlog"]["pending"] >= 1

        list_resp = await async_client.get(
            "/api/v1/audit/jobs/slo/evidence", params={"limit": 10}
        )
        assert list_resp.status_code == 200
        listed = list_resp.json()
        assert listed["total"] >= 1
        assert listed["items"][0]["job_slo"]["window_hours"] == 1

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type == AuditEventType.JOBS_SLO_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
