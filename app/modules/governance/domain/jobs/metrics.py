from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus


TERMINAL_JOB_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.DEAD_LETTER.value,
}


async def compute_job_slo(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    window_hours: int,
    target_success_rate_percent: float,
) -> dict[str, Any]:
    """
    Compute per-job-type reliability SLO metrics for a rolling window.

    We intentionally compute SLOs over *terminal* jobs only to avoid penalizing
    success rates for work that is still pending/running. Backlog is reported
    separately via `compute_job_backlog_snapshot`.
    """
    window_hours_int = int(window_hours)
    target_percent = float(target_success_rate_percent)

    window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours_int)
    result = await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.created_at >= window_start,
            sa.not_(BackgroundJob.is_deleted),
            BackgroundJob.status.in_(sorted(TERMINAL_JOB_STATUSES)),
        )
    )
    jobs = list(result.scalars().all())

    grouped: dict[str, list[BackgroundJob]] = {}
    for job in jobs:
        grouped.setdefault(str(job.job_type), []).append(job)

    metrics: list[dict[str, Any]] = []
    for job_type, items in sorted(grouped.items(), key=lambda pair: pair[0]):
        total = len(items)
        successful = sum(1 for j in items if j.status == JobStatus.COMPLETED.value)
        failed = sum(
            1
            for j in items
            if j.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
        )
        success_rate = round((successful / total) * 100.0, 2) if total else 0.0
        meets_slo = total > 0 and success_rate >= target_percent

        latest_completed: datetime | None = None
        durations: list[float] = []
        for j in items:
            if j.completed_at and (
                latest_completed is None or j.completed_at > latest_completed
            ):
                latest_completed = j.completed_at
            if j.started_at and j.completed_at:
                delta = (j.completed_at - j.started_at).total_seconds()
                if delta >= 0:
                    durations.append(delta)

        avg_duration = round(sum(durations) / len(durations), 2) if durations else None
        p95_duration = None
        if durations:
            sorted_durations = sorted(durations)
            index = max(0, math.ceil(len(sorted_durations) * 0.95) - 1)
            p95_duration = round(sorted_durations[index], 2)

        metrics.append(
            {
                "job_type": job_type,
                "window_hours": window_hours_int,
                "target_success_rate_percent": round(target_percent, 2),
                "total_jobs": total,
                "successful_jobs": successful,
                "failed_jobs": failed,
                "success_rate_percent": success_rate,
                "meets_slo": meets_slo,
                "latest_completed_at": latest_completed.isoformat()
                if latest_completed
                else None,
                "avg_duration_seconds": avg_duration,
                "p95_duration_seconds": p95_duration,
            }
        )

    available = [m for m in metrics if int(m.get("total_jobs", 0)) > 0]
    overall_meets = bool(available) and all(bool(m.get("meets_slo")) for m in available)

    return {
        "window_hours": window_hours_int,
        "target_success_rate_percent": round(target_percent, 2),
        "overall_meets_slo": overall_meets,
        "metrics": metrics,
    }


async def compute_job_backlog_snapshot(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    """
    Compute current backlog signals (queue depth + oldest pending age) for backpressure evidence.
    """
    now = datetime.now(timezone.utc)

    counts = dict.fromkeys(
        [
            JobStatus.PENDING.value,
            JobStatus.RUNNING.value,
            JobStatus.COMPLETED.value,
            JobStatus.FAILED.value,
            JobStatus.DEAD_LETTER.value,
        ],
        0,
    )
    result = await db.execute(
        select(BackgroundJob.status, func.count(BackgroundJob.id))
        .where(BackgroundJob.tenant_id == tenant_id, sa.not_(BackgroundJob.is_deleted))
        .group_by(BackgroundJob.status)
    )
    for status, count in result.all():
        if status in counts:
            counts[status] = int(count)

    oldest_pending = await db.scalar(
        select(func.min(BackgroundJob.scheduled_for)).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.status == JobStatus.PENDING.value,
            sa.not_(BackgroundJob.is_deleted),
        )
    )
    oldest_pending_age_seconds: float | None = None
    oldest_pending_scheduled_for: str | None = None
    if isinstance(oldest_pending, datetime):
        # SQLite often returns naive datetimes even when columns are timezone-aware.
        # Treat naive values as UTC for consistent backlog age math.
        if oldest_pending.tzinfo is None:
            oldest_pending = oldest_pending.replace(tzinfo=timezone.utc)
        oldest_pending_scheduled_for = oldest_pending.isoformat()
        oldest_pending_age_seconds = max(0.0, (now - oldest_pending).total_seconds())

    return {
        "captured_at": now.isoformat(),
        "pending": int(counts[JobStatus.PENDING.value]),
        "running": int(counts[JobStatus.RUNNING.value]),
        "completed": int(counts[JobStatus.COMPLETED.value]),
        "failed": int(counts[JobStatus.FAILED.value]),
        "dead_letter": int(counts[JobStatus.DEAD_LETTER.value]),
        "oldest_pending_scheduled_for": oldest_pending_scheduled_for,
        "oldest_pending_age_seconds": round(oldest_pending_age_seconds, 2)
        if oldest_pending_age_seconds is not None
        else None,
    }
