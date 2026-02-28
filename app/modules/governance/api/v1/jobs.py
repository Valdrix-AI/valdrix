"""
Background Jobs API - Job Queue Management

Provides endpoints for:
- Processing pending jobs (called by pg_cron or manually)
- Viewing job status
- Enqueueing new jobs
"""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal, Dict, Any, List
from datetime import datetime, timezone
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from app.shared.db.session import get_db, async_session_maker, mark_session_system_context
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.modules.governance.domain.jobs.processor import JobProcessor, enqueue_job
from app.shared.core.rate_limit import standard_limit
import structlog
import secrets
import asyncio
import json
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["Background Jobs"])
logger = structlog.get_logger()
_active_sse_connections: Dict[str, int] = {}
_active_sse_lock = asyncio.Lock()


async def require_internal_job_secret(
    secret: str = Query(..., description="Internal secret for pg_cron"),
) -> None:
    """
    Enforce internal scheduler authentication for /jobs/internal/process.

    Defined as a dependency so auth-coverage audits can assert this endpoint is
    intentionally protected without user-token RBAC.
    """
    from app.shared.core.config import get_settings

    settings = get_settings()
    expected_secret = settings.INTERNAL_JOB_SECRET
    if not expected_secret or len(expected_secret) < 32:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_JOB_SECRET is not configured securely. Set a 32+ character secret.",
        )
    if not secrets.compare_digest(secret, expected_secret):
        raise HTTPException(status_code=403, detail="Invalid secret")


class JobStatusResponse(BaseModel):
    """Response with job queue statistics."""

    pending: int
    running: int
    completed: int
    failed: int
    dead_letter: int


class JobSLOMetric(BaseModel):
    job_type: str
    window_hours: int
    target_success_rate_percent: float
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    success_rate_percent: float
    meets_slo: bool
    latest_completed_at: str | None = None
    avg_duration_seconds: float | None = None
    p95_duration_seconds: float | None = None


class JobSLOResponse(BaseModel):
    window_hours: int
    target_success_rate_percent: float
    overall_meets_slo: bool
    metrics: list[JobSLOMetric]


class ProcessJobsResponse(BaseModel):
    """Response after processing jobs."""

    processed: int
    succeeded: int
    failed: int


class EnqueueJobRequest(BaseModel):
    """Request to enqueue a new job."""

    job_type: JobType
    payload: Dict[str, Any] | None = None
    scheduled_for: datetime | None = None


class JobResponse(BaseModel):
    """Single job details."""

    id: uuid.UUID
    job_type: JobType
    status: str
    attempts: int
    scheduled_for: datetime
    created_at: datetime
    error_message: str | None = None


@router.get("/status", response_model=JobStatusResponse)
async def get_job_queue_status(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
) -> JobStatusResponse:
    """
    Get current job queue statistics.

    Requires admin role.
    """
    # Count jobs by status
    result = await db.execute(
        select(BackgroundJob.status, func.count(BackgroundJob.id))
        .where(BackgroundJob.tenant_id == user.tenant_id)
        .where(sa.not_(BackgroundJob.is_deleted))
        .group_by(BackgroundJob.status)
    )

    counts = {row[0]: row[1] for row in result.all()}

    return JobStatusResponse(
        pending=counts.get(JobStatus.PENDING, 0),
        running=counts.get(JobStatus.RUNNING, 0),
        completed=counts.get(JobStatus.COMPLETED, 0),
        failed=counts.get(JobStatus.FAILED, 0),
        dead_letter=counts.get(JobStatus.DEAD_LETTER, 0),
    )


@router.get("/slo", response_model=JobSLOResponse)
async def get_job_slo(
    user: Annotated[
        CurrentUser,
        Depends(requires_feature(FeatureFlag.AUDIT_LOGS, required_role="admin")),
    ],
    window_hours: int = Query(default=24 * 7, ge=1, le=24 * 30),
    target_success_rate_percent: float = Query(default=95.0, ge=0, le=100),
    db: AsyncSession = Depends(get_db),
) -> JobSLOResponse:
    """
    Job reliability SLO metrics for a rolling window.

    This is intended for production readiness evidence (availability and job success rates).
    """
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required.")

    from app.modules.governance.domain.jobs.metrics import compute_job_slo

    computed = await compute_job_slo(
        db,
        tenant_id=user.tenant_id,
        window_hours=int(window_hours),
        target_success_rate_percent=float(target_success_rate_percent),
    )
    metrics: list[JobSLOMetric] = [
        JobSLOMetric(**m) for m in computed.get("metrics", [])
    ]
    return JobSLOResponse(
        window_hours=int(computed.get("window_hours", window_hours)),
        target_success_rate_percent=float(
            computed.get("target_success_rate_percent", target_success_rate_percent)
        ),
        overall_meets_slo=bool(computed.get("overall_meets_slo", False)),
        metrics=metrics,
    )


@router.post("/process", response_model=ProcessJobsResponse)
@standard_limit
async def process_pending_jobs(
    request: Request,
    _user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=50, description="Max jobs to process"),
) -> ProcessJobsResponse:
    """
    Process pending jobs manually.

    This endpoint is typically called by pg_cron every minute,
    but can be triggered manually by admins.
    """
    processor = JobProcessor(db)
    results = await processor.process_pending_jobs(limit=limit)

    return ProcessJobsResponse(
        processed=results["processed"],
        succeeded=results["succeeded"],
        failed=results["failed"],
    )


@router.post("/enqueue", response_model=JobResponse)
async def enqueue_new_job(
    request: EnqueueJobRequest,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
) -> JobResponse:
    """
    Enqueue a new background job.

    Job types:
    - finops_analysis: Run FinOps analysis
    - zombie_scan: Scan for zombie resources
    - notification: Send notification
    """
    # Validate job type - Item N1: Prevent enqueuing internal system jobs
    USER_CREATABLE_JOBS = {
        JobType.FINOPS_ANALYSIS,
        JobType.ZOMBIE_SCAN,
        JobType.NOTIFICATION,
    }
    if request.job_type not in USER_CREATABLE_JOBS:
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized job type. Users can only enqueue: {[t.value for t in USER_CREATABLE_JOBS]}",
        )

    job = await enqueue_job(
        db=db,
        job_type=request.job_type,
        tenant_id=user.tenant_id,
        payload=request.payload,
        scheduled_for=request.scheduled_for or datetime.now(timezone.utc),
    )

    return JobResponse(
        id=job.id,
        job_type=JobType(job.job_type),
        status=job.status,
        attempts=job.attempts,
        scheduled_for=job.scheduled_for,
        created_at=job.created_at,
    )


@router.get("/list", response_model=list[JobResponse])
async def list_jobs(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: Literal["created_at", "scheduled_for", "status"] = Query("created_at"),
    order: Literal["asc", "desc"] = Query(default="desc"),
) -> List[JobResponse]:
    """List recent jobs for the tenant."""
    sort_column = getattr(BackgroundJob, sort_by)
    order_func = desc if order == "desc" else asc

    query = (
        select(BackgroundJob)
        .where(BackgroundJob.tenant_id == user.tenant_id)
        .where(sa.not_(BackgroundJob.is_deleted))
    )

    if status:
        query = query.where(BackgroundJob.status == status)

    query = query.order_by(order_func(sort_column)).limit(limit)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return [
        JobResponse(
            id=j.id,
            job_type=JobType(j.job_type),
            status=j.status,
            attempts=j.attempts,
            scheduled_for=j.scheduled_for,
            created_at=j.created_at,
            # Item 19: Sanitize error messages (hide internal details)
            error_message=j.error_message.split(":")[0]
            if j.error_message and ":" in j.error_message
            else j.error_message,
        )
        for j in jobs
    ]


@router.get("/stream")
async def stream_job_updates(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
) -> EventSourceResponse:
    """
    Stream real-time job status updates for the tenant.

    This uses Server-Sent Events (SSE) to push updates to the frontend
    whenever a job status changes or a new job is enqueued.
    """
    from app.shared.core.config import get_settings

    settings = get_settings()
    tenant_key = str(user.tenant_id)
    max_connections = max(1, int(settings.SSE_MAX_CONNECTIONS_PER_TENANT))
    poll_interval = max(1, int(settings.SSE_POLL_INTERVAL_SECONDS))

    async with _active_sse_lock:
        current_connections = _active_sse_connections.get(tenant_key, 0)
        if current_connections >= max_connections:
            raise HTTPException(
                status_code=429,
                detail=f"Too many active job streams for tenant. Max allowed: {max_connections}",
            )
        _active_sse_connections[tenant_key] = current_connections + 1

    async def event_generator() -> AsyncIterator[Dict[str, str]]:
        last_seen_job_states: Dict[str, str] = {}
        try:
            while True:
                try:
                    # We use a fresh session to avoid stale data
                    async with async_session_maker() as session:
                        await mark_session_system_context(session)
                        # Fetch active jobs (pending, running) and recently finished ones
                        query = (
                            select(BackgroundJob)
                            .where(BackgroundJob.tenant_id == user.tenant_id)
                            .where(sa.not_(BackgroundJob.is_deleted))
                            .where(
                                sa.or_(
                                    BackgroundJob.status.in_(
                                        [JobStatus.PENDING, JobStatus.RUNNING]
                                    ),
                                    sa.and_(
                                        BackgroundJob.status.in_(
                                            [JobStatus.COMPLETED, JobStatus.FAILED]
                                        ),
                                        BackgroundJob.updated_at
                                        >= datetime.now(timezone.utc).replace(
                                            second=0, microsecond=0
                                        ),
                                    ),
                                )
                            )
                            .order_by(desc(BackgroundJob.updated_at))
                            .limit(20)
                        )

                        result = await session.execute(query)
                        jobs = result.scalars().all()

                        updates = []
                        for job in jobs:
                            job_id_str = str(job.id)
                            current_state = f"{job.status}:{job.updated_at.isoformat()}"

                            if last_seen_job_states.get(job_id_str) != current_state:
                                last_seen_job_states[job_id_str] = current_state
                                updates.append(
                                    {
                                        "id": job_id_str,
                                        "job_type": job.job_type,
                                        "status": job.status,
                                        "updated_at": job.updated_at.isoformat(),
                                        "error_message": job.error_message.split(":")[0]
                                        if job.error_message
                                        and ":" in job.error_message
                                        else job.error_message,
                                    }
                                )

                        if updates:
                            yield {"event": "job_update", "data": json.dumps(updates)}

                        # Heartbeat to keep connection alive
                        yield {"event": "ping", "data": "heartbeat"}

                except Exception as e:
                    logger.error("SSE Stream Error", error=str(e))
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": "Stream interrupted"}),
                    }

                await asyncio.sleep(poll_interval)
        finally:
            async with _active_sse_lock:
                remaining = _active_sse_connections.get(tenant_key, 0) - 1
                if remaining > 0:
                    _active_sse_connections[tenant_key] = remaining
                else:
                    _active_sse_connections.pop(tenant_key, None)

    return EventSourceResponse(event_generator())


# Internal endpoint for pg_cron (no auth, called by database)
@router.post("/internal/process")
async def internal_process_jobs(
    background_tasks: BackgroundTasks,
    _db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_internal_job_secret),
) -> Dict[str, str]:
    """
    Internal endpoint called by pg_cron (Asynchronous).
    """
    async def run_processor() -> None:
        async with async_session_maker() as session:
            await mark_session_system_context(session)
            processor = JobProcessor(session)
            await processor.process_pending_jobs()

    background_tasks.add_task(run_processor)

    return {"status": "accepted", "message": "Job processing started in background"}
