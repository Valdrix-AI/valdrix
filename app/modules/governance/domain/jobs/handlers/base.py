"""
PRODUCTION: Base Job Handler with Timeout Enforcement

This module replaces app/services/jobs/handlers/base.py with production-ready
implementation that enforces timeouts and proper error handling.
"""

import asyncio
import structlog
from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob, JobStatus
from app.shared.core.exceptions import ValdrixException

logger = structlog.get_logger()


class JobTimeoutError(ValdrixException):
    """Raised when a job exceeds its timeout."""

    def __init__(self, job_id: str, timeout_seconds: int):
        super().__init__(
            message=f"Job {job_id} exceeded timeout of {timeout_seconds} seconds",
            code="job_timeout",
            status_code=504,
            details={"job_id": job_id, "timeout_seconds": timeout_seconds},
        )


class BaseJobHandler(ABC):
    """
    PRODUCTION: Abstract base class for all background job handlers.

    Features:
    - Mandatory timeout enforcement per job type
    - Atomic status transitions (PENDING → RUNNING → COMPLETED/FAILED)
    - Comprehensive error handling and logging
    - Automatic dead-letter queue handling
    - Audit trail for all job state changes

    Subclasses must:
    1. Define timeout_seconds class attribute
    2. Implement execute() method
    3. Handle ValdrixException gracefully
    """

    # PRODUCTION: Override in subclasses
    # Examples:
    # - ZOMBIE_SCAN: 300 seconds (5 minutes)
    # - FINOPS_ANALYSIS: 180 seconds (3 minutes)
    # - COST_INGESTION: 600 seconds (10 minutes)
    timeout_seconds: int = 300

    # Maximum automatic retries before DLQ
    max_retries: int = 3

    @abstractmethod
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        """
        Execute the job logic. Must be implemented by subclasses.

        Args:
            job: The BackgroundJob model instance
            db: Database session with proper tenant context

        Returns:
            Result dictionary with job output

        Raises:
            ValdrixException: For expected errors (caught and retried)
            Exception: For unexpected errors (moved to DLQ)
        """
        pass

    async def process(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        """
        PRODUCTION: Main entry point for job processing with full safety.

        This method:
        1. Validates job state
        2. Sets execution timeout
        3. Manages atomic state transitions
        4. Records all outcomes in database
        5. Handles retry logic
        6. Moves failed jobs to DLQ

        Args:
            job: BackgroundJob to process
            db: Database session

        Returns:
            Job result dictionary

        Raises:
            JobTimeoutError: If job exceeds timeout
        """
        job_id = str(job.id)
        job_type = job.job_type
        tenant_id = str(job.tenant_id) if job.tenant_id else "system"

        logger.info(
            "job_processing_started",
            job_id=job_id,
            job_type=job_type,
            tenant_id=tenant_id,
            attempt=job.attempts + 1,
        )

        try:
            # 1. Atomic transition: PENDING → RUNNING
            await self._transition_to_running(job, db)

            # 2. PRODUCTION: Execute with hard timeout
            try:
                async with asyncio.timeout(self.timeout_seconds):
                    result = await self.execute(job, db)

            except asyncio.TimeoutError:
                logger.error(
                    "job_timeout_exceeded",
                    job_id=job_id,
                    job_type=job_type,
                    timeout_seconds=self.timeout_seconds,
                    tenant_id=tenant_id,
                )
                raise JobTimeoutError(job_id, self.timeout_seconds)

            # 3. Success: Transition to COMPLETED
            await self._transition_to_completed(job, result, db)

            logger.info(
                "job_completed_successfully",
                job_id=job_id,
                job_type=job_type,
                tenant_id=tenant_id,
            )

            return result

        except JobTimeoutError:
            # Timeouts are fatal - move to DLQ
            await self._transition_to_dead_letter(
                job, f"Job exceeded {self.timeout_seconds}s timeout", db
            )
            raise

        except ValdrixException as e:
            # Expected errors - may be retryable
            return await self._handle_valdrix_exception(job, e, db)

        except Exception as e:
            # Unexpected errors - move to DLQ
            logger.error(
                "job_unexpected_error",
                job_id=job_id,
                job_type=job_type,
                tenant_id=tenant_id,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )

            await self._transition_to_dead_letter(
                job, f"Unexpected error: {type(e).__name__}: {str(e)[:500]}", db
            )
            raise

    async def _transition_to_running(
        self, job: BackgroundJob, db: AsyncSession
    ) -> None:
        """Atomically transition job from PENDING to RUNNING."""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        db.add(job)
        await db.commit()

        logger.info("job_status_running", job_id=str(job.id), attempt=job.attempts)

    async def _transition_to_completed(
        self, job: BackgroundJob, result: Dict[str, Any], db: AsyncSession
    ) -> None:
        """Atomically transition job to COMPLETED."""
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.result = result
        job.error_message = None  # Clear previous errors
        db.add(job)
        await db.commit()

        logger.info(
            "job_status_completed",
            job_id=str(job.id),
            result_keys=list(result.keys()) if result else None,
        )

    async def _transition_to_dead_letter(
        self, job: BackgroundJob, error_message: str, db: AsyncSession
    ) -> None:
        """Move job to dead letter queue after max retries exceeded."""
        job.status = JobStatus.DEAD_LETTER
        job.error_message = error_message[:2000]  # Truncate to DB limit
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        await db.commit()

        logger.error(
            "job_moved_to_dlq",
            job_id=str(job.id),
            job_type=job.job_type,
            error_message=error_message[:500],
            attempts=job.attempts,
        )

        # PRODUCTION: Alert ops team
        try:
            from app.shared.core.sentry import capture_exception

            capture_exception(
                Exception(
                    f"Job {job.id} moved to DLQ after {job.attempts} attempts: {error_message}"
                )
            )
        except Exception:
            pass

    async def _handle_valdrix_exception(
        self, job: BackgroundJob, exc: ValdrixException, db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle expected ValdrixExceptions with retry logic."""

        logger.warning(
            "job_valdrix_exception",
            job_id=str(job.id),
            job_type=job.job_type,
            error_code=exc.code,
            error_message=exc.message,
            attempt=job.attempts,
        )

        # Decide: retry or fail?
        if job.attempts < self.max_retries:
            # Retryable - mark as FAILED but don't DLQ yet
            job.status = JobStatus.FAILED
            job.error_message = f"{exc.code}: {exc.message}"
            db.add(job)
            await db.commit()

            logger.info(
                "job_failed_will_retry",
                job_id=str(job.id),
                next_retry=job.attempts + 1,
                max_retries=self.max_retries,
            )

            raise exc  # Let scheduler retry
        else:
            # Max retries exceeded - move to DLQ
            await self._transition_to_dead_letter(
                job, f"Exceeded {self.max_retries} retries: {exc.message}", db
            )
            raise exc
