"""
Background Jobs API - Job Queue Management

Provides endpoints for:
- Processing pending jobs (called by pg_cron or manually)
- Viewing job status
- Enqueueing new jobs
"""

from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from pydantic import BaseModel
from app.db.session import get_db, async_session_maker
from app.core.auth import CurrentUser, requires_role
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.services.jobs.processor import JobProcessor, enqueue_job
import structlog

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])
logger = structlog.get_logger()


class JobStatusResponse(BaseModel):
    """Response with job queue statistics."""
    pending: int
    running: int
    completed: int
    failed: int
    dead_letter: int


class ProcessJobsResponse(BaseModel):
    """Response after processing jobs."""
    processed: int
    succeeded: int
    failed: int


class EnqueueJobRequest(BaseModel):
    """Request to enqueue a new job."""
    job_type: str
    payload: dict | None = None
    scheduled_for: datetime | None = None


class JobResponse(BaseModel):
    """Single job details."""
    id: str
    job_type: str
    status: str
    attempts: int
    scheduled_for: datetime
    created_at: datetime
    error_message: str | None = None


@router.get("/status", response_model=JobStatusResponse)
async def get_job_queue_status(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
):
    """
    Get current job queue statistics.
    
    Requires admin role.
    """
    # Count jobs by status
    result = await db.execute(
        select(
            BackgroundJob.status,
            func.count(BackgroundJob.id)
        )
        .where(BackgroundJob.tenant_id == user.tenant_id)
        .group_by(BackgroundJob.status)
    )
    
    counts = {row[0]: row[1] for row in result.all()}
    
    return JobStatusResponse(
        pending=counts.get(JobStatus.PENDING, 0),
        running=counts.get(JobStatus.RUNNING, 0),
        completed=counts.get(JobStatus.COMPLETED, 0),
        failed=counts.get(JobStatus.FAILED, 0),
        dead_letter=counts.get(JobStatus.DEAD_LETTER, 0)
    )


@router.post("/process", response_model=ProcessJobsResponse)
async def process_pending_jobs(
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=10, le=50, description="Max jobs to process")
):
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
        failed=results["failed"]
    )


@router.post("/enqueue", response_model=JobResponse)
async def enqueue_new_job(
    request: EnqueueJobRequest,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db)
):
    """
    Enqueue a new background job.
    
    Job types:
    - finops_analysis: Run FinOps analysis
    - zombie_scan: Scan for zombie resources
    - notification: Send notification
    """
    # Validate job type
    valid_types = [t.value for t in JobType]
    if request.job_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_type. Valid types: {valid_types}"
        )
    
    job = await enqueue_job(
        db=db,
        job_type=request.job_type,
        tenant_id=user.tenant_id,
        payload=request.payload,
        scheduled_for=request.scheduled_for or datetime.now(timezone.utc)
    )
    
    return JobResponse(
        id=str(job.id),
        job_type=job.job_type,
        status=job.status,
        attempts=job.attempts,
        scheduled_for=job.scheduled_for,
        created_at=job.created_at
    )


@router.get("/list", response_model=list[JobResponse])
async def list_jobs(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, le=100)
):
    """List recent jobs for the tenant."""
    query = (
        select(BackgroundJob)
        .where(BackgroundJob.tenant_id == user.tenant_id)
        .order_by(BackgroundJob.created_at.desc())
        .limit(limit)
    )
    
    if status:
        query = query.where(BackgroundJob.status == status)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return [
        JobResponse(
            id=str(j.id),
            job_type=j.job_type,
            status=j.status,
            attempts=j.attempts,
            scheduled_for=j.scheduled_for,
            created_at=j.created_at,
            error_message=j.error_message
        )
        for j in jobs
    ]


# Internal endpoint for pg_cron (no auth, called by database)
@router.post("/internal/process")
async def internal_process_jobs(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(description="Internal secret for pg_cron")
):
    """
    Internal endpoint called by pg_cron (Asynchronous).
    """
    from app.core.config import get_settings
    settings = get_settings()
    
    # Validate internal secret
    expected_secret = getattr(settings, 'INTERNAL_JOB_SECRET', 'dev-secret')
    if secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")
    
    async def run_processor():
        async with async_session_maker() as session:
            processor = JobProcessor(session)
            await processor.process_pending_jobs()

    background_tasks.add_task(run_processor)
    
    return {"status": "accepted", "message": "Job processing started in background"}
