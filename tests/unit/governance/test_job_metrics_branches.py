from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.background_job import BackgroundJob, JobStatus
from app.modules.governance.domain.jobs.metrics import (
    compute_job_backlog_snapshot,
    compute_job_slo,
)


def _job(
    *,
    tenant_id,
    job_type: str,
    status: str,
    created_at: datetime,
    scheduled_for: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    is_deleted: bool = False,
) -> BackgroundJob:
    return BackgroundJob(
        job_type=job_type,
        tenant_id=tenant_id,
        status=status,
        scheduled_for=scheduled_for,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        is_deleted=is_deleted,
    )


@pytest.mark.asyncio
async def test_compute_job_slo_groups_terminal_jobs_and_computes_percentiles(
    db, test_tenant
) -> None:
    now = datetime.now(timezone.utc)
    other_tenant = uuid4()
    jobs = [
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(hours=2),
            scheduled_for=now - timedelta(hours=2),
            started_at=now - timedelta(hours=2, minutes=5),
            completed_at=now - timedelta(hours=2),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
            started_at=now - timedelta(hours=1, minutes=1),
            completed_at=now - timedelta(hours=1),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.FAILED.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="zombie_scan",
            status=JobStatus.DEAD_LETTER.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.PENDING.value,
            created_at=now - timedelta(minutes=30),
            scheduled_for=now - timedelta(minutes=30),
        ),
        _job(
            tenant_id=other_tenant,
            job_type="finops_analysis",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
            started_at=now - timedelta(hours=1, minutes=3),
            completed_at=now - timedelta(hours=1),
        ),
    ]
    db.add_all(jobs)
    await db.commit()

    payload = await compute_job_slo(
        db,
        tenant_id=test_tenant.id,
        window_hours=24,
        target_success_rate_percent=60,
    )

    assert payload["window_hours"] == 24
    assert payload["target_success_rate_percent"] == 60.0
    assert payload["overall_meets_slo"] is False
    metrics = {row["job_type"]: row for row in payload["metrics"]}
    finops = metrics["finops_analysis"]
    assert finops["total_jobs"] == 3
    assert finops["successful_jobs"] == 2
    assert finops["failed_jobs"] == 1
    assert finops["success_rate_percent"] == 66.67
    assert finops["meets_slo"] is True
    assert finops["avg_duration_seconds"] == 180.0
    assert finops["p95_duration_seconds"] == 300.0
    assert finops["latest_completed_at"] is not None
    assert metrics["zombie_scan"]["meets_slo"] is False


@pytest.mark.asyncio
async def test_compute_job_slo_returns_empty_metrics_for_no_terminal_jobs(
    db, test_tenant
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.PENDING.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
        )
    )
    await db.commit()

    payload = await compute_job_slo(
        db,
        tenant_id=test_tenant.id,
        window_hours=24,
        target_success_rate_percent=99,
    )

    assert payload["overall_meets_slo"] is False
    assert payload["metrics"] == []


@pytest.mark.asyncio
async def test_compute_job_backlog_snapshot_counts_and_oldest_pending_age(
    db, test_tenant
) -> None:
    now = datetime.now(timezone.utc)
    naive_oldest = datetime.now() - timedelta(hours=2)
    jobs = [
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.PENDING.value,
            created_at=now - timedelta(hours=2),
            scheduled_for=naive_oldest,
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.PENDING.value,
            created_at=now - timedelta(hours=1),
            scheduled_for=now - timedelta(hours=1),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.RUNNING.value,
            created_at=now - timedelta(minutes=20),
            scheduled_for=now - timedelta(minutes=20),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.COMPLETED.value,
            created_at=now - timedelta(minutes=10),
            scheduled_for=now - timedelta(minutes=10),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.FAILED.value,
            created_at=now - timedelta(minutes=10),
            scheduled_for=now - timedelta(minutes=10),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.DEAD_LETTER.value,
            created_at=now - timedelta(minutes=10),
            scheduled_for=now - timedelta(minutes=10),
        ),
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.PENDING.value,
            created_at=now - timedelta(minutes=5),
            scheduled_for=now - timedelta(minutes=5),
            is_deleted=True,
        ),
    ]
    db.add_all(jobs)
    await db.commit()

    snapshot = await compute_job_backlog_snapshot(db, tenant_id=test_tenant.id)

    assert snapshot["pending"] == 2
    assert snapshot["running"] == 1
    assert snapshot["completed"] == 1
    assert snapshot["failed"] == 1
    assert snapshot["dead_letter"] == 1
    assert snapshot["oldest_pending_scheduled_for"] is not None
    assert snapshot["oldest_pending_age_seconds"] is not None
    assert snapshot["oldest_pending_age_seconds"] > 0


@pytest.mark.asyncio
async def test_compute_job_backlog_snapshot_handles_no_pending(db, test_tenant) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        _job(
            tenant_id=test_tenant.id,
            job_type="finops_analysis",
            status=JobStatus.RUNNING.value,
            created_at=now - timedelta(minutes=5),
            scheduled_for=now - timedelta(minutes=5),
        )
    )
    await db.commit()

    snapshot = await compute_job_backlog_snapshot(db, tenant_id=test_tenant.id)

    assert snapshot["pending"] == 0
    assert snapshot["oldest_pending_scheduled_for"] is None
    assert snapshot["oldest_pending_age_seconds"] is None
