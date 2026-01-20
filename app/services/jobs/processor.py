"""
Job Processor Service - Phase 7: Scheduler SPOF Resolution

Processes background jobs from the database queue.
Works with pg_cron to provide durable, distributed job processing.

Key Features:
- Survives app restarts (jobs in database)
- Automatic retries with exponential backoff
- Per-tenant job isolation
- Full audit trail

Usage:
    processor = JobProcessor(db)
    await processor.process_pending_jobs()
"""

import sqlalchemy as sa
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
import structlog
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus
from app.services.jobs.handlers import get_handler_factory

logger = structlog.get_logger()

# Job processing configuration
MAX_JOBS_PER_BATCH = 10
JOB_LOCK_TIMEOUT_MINUTES = 30
BACKOFF_BASE_SECONDS = 60
JOB_TIMEOUT_SECONDS = 300  # 5 minutes default timeout


class JobProcessor:
    """
    Processes background jobs from the database queue.
    
    Designed to be called by:
    1. pg_cron (every minute in Supabase)
    2. API endpoint for on-demand processing
    3. Startup hook for catching up
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    
    
    async def process_pending_jobs(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Process pending jobs up to the limit with OTel tracing.
        """
        limit = limit or MAX_JOBS_PER_BATCH
        from app.core.tracing import get_tracer
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span("process_pending_jobs") as span:
            span.set_attribute("batch_limit", limit)
            logger.info("processing_pending_jobs", limit=limit)
            results = {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "errors": []
            }
            
            try:
                # Fetch pending jobs that are due
                pending_jobs = await self._fetch_pending_jobs(limit)
                
                logger.info(
                    "job_processor_batch_start",
                    pending_count=len(pending_jobs)
                )
                
                for job in pending_jobs:
                    try:
                        await self._process_single_job(job)
                        results["succeeded"] += 1
                    except (KeyError, ValueError) as e:
                        # Handler configuration/payload errors
                        logger.warning("job_handler_config_error", job_id=str(job.id), error=str(e))
                        results["failed"] += 1
                        results["errors"].append({"job_id": str(job.id), "error": str(e), "type": "config"})
                    except Exception as e:  # noqa: BLE001 - Intentional catch-all for job isolation
                        results["failed"] += 1
                        results["errors"].append({"job_id": str(job.id), "error": str(e)})
                    results["processed"] += 1
                
                logger.info(
                    "job_processor_batch_complete",
                    **results
                )
                
            except sa.exc.SQLAlchemyError as e:
                logger.error("job_processor_batch_db_error", error=str(e))
                results["errors"].append({"batch_error": str(e)})
            except Exception as e:
                logger.error("job_processor_batch_unexpected_error", error=str(e))
                results["errors"].append({"batch_error": str(e)})
            
            return results
    
    async def _fetch_pending_jobs(self, limit: int) -> list[BackgroundJob]:
        """
        Fetch pending jobs that are ready to run.
        Uses SELECT FOR UPDATE SKIP LOCKED for high-concurrency safety.
        """
        now = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(BackgroundJob)
            .where(
                BackgroundJob.status == JobStatus.PENDING.value,
                BackgroundJob.scheduled_for <= now,
                BackgroundJob.attempts < BackgroundJob.max_attempts,
                BackgroundJob.is_deleted == False
            )
            # BE-SCHED-5: Order by priority (desc) first, then scheduled_for
            .order_by(BackgroundJob.priority.desc(), BackgroundJob.scheduled_for)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        found = list(result.scalars().all())
        return found

    
    async def _process_single_job(self, job: BackgroundJob) -> None:
        """Process a single job with error handling and tracing."""
        from app.core.tracing import get_tracer
        tracer = get_tracer(__name__)
        
        with tracer.start_as_current_span(f"job_process:{job.job_type}") as span:
            span.set_attribute("job_id", str(job.id))
            span.set_attribute("tenant_id", str(job.tenant_id) if job.tenant_id else "system")
            
            logger.info(
                "job_processing_start",
                job_id=str(job.id),
                job_type=job.job_type,
                attempt=job.attempts + 1
            )
        
        # Mark as running
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        await self.db.commit()
        
        result = None
        
        try:
            # Get and instantiate handler for job type
            job_type_key = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type)
            handler_cls = get_handler_factory(job_type_key)
            handler = handler_cls()
            
            # Use a savepoint to isolate this job's database changes
            async with self.db.begin_nested():
                # Set tenant context for RLS isolation during job execution
                if job.tenant_id:
                    await self.db.execute(
                        sa.text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                        {"tid": str(job.tenant_id)}
                    )
                
                # Execute handler with timeout protection (BE-SCHED-2)
                result = await asyncio.wait_for(
                    handler.execute(job, self.db),
                    timeout=JOB_TIMEOUT_SECONDS
                )
            
            # Mark as completed
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.now(timezone.utc)
            job.result = result
            job.error_message = None
            
            logger.info(
                "job_processing_success",
                job_id=str(job.id),
                job_type=job.job_type
            )
            
        except asyncio.TimeoutError:
            logger.error(
                "job_processing_timeout",
                job_id=str(job.id),
                job_type=job.job_type,
                timeout_seconds=JOB_TIMEOUT_SECONDS
            )
            job.error_message = f"Job timed out after {JOB_TIMEOUT_SECONDS}s"
            job.status = JobStatus.FAILED.value
            
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.DEAD_LETTER.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                backoff_seconds = BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1))
                job.status = JobStatus.PENDING.value
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                
        except asyncio.CancelledError:
            logger.warning("job_processing_cancelled", job_id=str(job.id))
            job.error_message = "Job was cancelled"
            job.status = JobStatus.PENDING.value
            job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=60)
            
        except Exception as e:  # noqa: BLE001 - Intentional catch-all for resilience
            logger.error(
                "job_processing_failed",
                job_id=str(job.id),
                job_type=job.job_type,
                error=str(e)
            )
            
            job.error_message = str(e)
            job.status = JobStatus.FAILED.value
            
            if job.attempts >= job.max_attempts:
                job.status = JobStatus.DEAD_LETTER.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                backoff_seconds = BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1))
                job.status = JobStatus.PENDING.value
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        
        await self.db.commit()


# ==================== Job Creation Helpers ====================


async def enqueue_job(
    db: AsyncSession,
    job_type: str,
    tenant_id: Optional[UUID] = None,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[datetime] = None,
    max_attempts: int = 3
) -> BackgroundJob:
    """
    Enqueue a new background job.
    
    Usage:
        job = await enqueue_job(
            db,
            job_type=JobType.FINOPS_ANALYSIS,
            tenant_id=tenant.id,
            payload={"force_refresh": True}
        )
    """
    job = BackgroundJob(
        job_type=job_type.value if hasattr(job_type, "value") else job_type,
        tenant_id=tenant_id,
        payload=payload,
        status=JobStatus.PENDING.value,
        scheduled_for=scheduled_for or datetime.now(timezone.utc),
        max_attempts=max_attempts,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(
        "job_enqueued",
        job_id=str(job.id),
        job_type=job_type,
        tenant_id=str(tenant_id) if tenant_id else None
    )
    
    return job
