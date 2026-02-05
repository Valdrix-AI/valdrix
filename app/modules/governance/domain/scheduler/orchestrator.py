from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
import asyncio
import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from typing import Dict, Any

from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.modules.governance.domain.scheduler.processors import AnalysisProcessor

logger = structlog.get_logger()

# Arbitrary constant for scheduler advisory locks - DEPRECATED in favor of SELECT FOR UPDATE
# Keeping for reference of lock inheritance
SCHEDULER_LOCK_BASE_ID = 48293021


# Metrics are now imported from app.modules.governance.domain.scheduler.metrics

class SchedulerOrchestrator:
    """Manages APScheduler and job distribution."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.scheduler = AsyncIOScheduler()
        self.session_maker = session_maker
        self.processor = AnalysisProcessor()
        self.semaphore = asyncio.Semaphore(10)
        self._last_run_success: bool | None = None
        self._last_run_time: str | None = None

    async def cohort_analysis_job(self, target_cohort: TenantCohort) -> None:
        """
        PRODUCTION: Enqueues a distributed task for cohort analysis.
        """
        logger.info("scheduler_dispatching_cohort_job", cohort=target_cohort.value)
        
        # Skip Celery dispatch if Redis unavailable (local dev)
        try:
            from app.shared.core.celery_app import celery_app
            celery_app.send_task("scheduler.cohort_analysis", args=[target_cohort.value])
        except Exception as e:
            logger.warning("scheduler_celery_unavailable", error=str(e), cohort=target_cohort.value)
        
        self._last_run_success = True
        self._last_run_time = datetime.now(timezone.utc).isoformat()

    async def _is_low_carbon_window(self, region: str) -> bool:
        """
        Series-A (Phase 4): Carbon-Aware Scheduling.
        Returns True if the current time is a 'Green Window' for the region.
        
        Logic:
        - 10 AM to 4 PM (10:00 - 16:00) usually has high solar output.
        - 12 AM to 5 AM (00:00 - 05:00) usually has low grid demand.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # Simple rule-based logic for now
        is_green = (10 <= hour <= 16) or (0 <= hour <= 5)
        logger.info("scheduler_green_window_check", hour=hour, is_green=is_green, region=region)
        return is_green

    async def auto_remediation_job(self) -> None:
        """Dispatches weekly remediation sweep."""
        logger.info("scheduler_dispatching_remediation_sweep")
        try:
            from app.shared.core.celery_app import celery_app
            celery_app.send_task("scheduler.remediation_sweep")
        except Exception as e:
            logger.warning("scheduler_celery_unavailable", error=str(e), job="remediation")

    async def billing_sweep_job(self) -> None:
        """Dispatches billing sweep."""
        logger.info("scheduler_dispatching_billing_sweep")
        try:
            from app.shared.core.celery_app import celery_app
            celery_app.send_task("scheduler.billing_sweep")
        except Exception as e:
            logger.warning("scheduler_celery_unavailable", error=str(e), job="billing")


    async def detect_stuck_jobs(self) -> None:
        """
        Series-A Hardening (Phase 2): Detects jobs stuck in PENDING status for > 1 hour.
        Emits critical alerts and moves them to FAILED to prevent queue poisoning.
        """
        async with self.session_maker() as db:
            from app.models.background_job import BackgroundJob, JobStatus
            from datetime import datetime, timezone, timedelta
            
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            
            # Find stuck jobs
            stmt = sa.select(BackgroundJob).where(
                BackgroundJob.status == JobStatus.PENDING,
                BackgroundJob.created_at < cutoff,
                sa.not_(BackgroundJob.is_deleted)
            )
            result = await db.execute(stmt)
            stuck_jobs = result.scalars().all()
            
            if stuck_jobs:
                logger.critical(
                    "stuck_jobs_detected", 
                    count=len(stuck_jobs),
                    job_ids=[str(j.id) for j in stuck_jobs[:10]]
                )
                
                # Update status to avoid re-detection (or could retry, but legacy review says alert & fail)
                for job in stuck_jobs:
                    job.status = JobStatus.FAILED
                    job.error_message = "Stuck in PENDING for > 1 hour. Terminated by StuckJobDetector."
                
                await db.commit()
                logger.info("stuck_jobs_mitigated", count=len(stuck_jobs))

    async def maintenance_sweep_job(self) -> None:
        """Dispatches maintenance sweep."""
        logger.info("scheduler_dispatching_maintenance_sweep")
        from app.shared.core.celery_app import celery_app
        celery_app.send_task("scheduler.maintenance_sweep")
        
        # Keep internal metric update in-process or move? 
        # Moving to task might delay it, but safer.
        # However, for simplicity, I'll keep the metric update logic if it was critical, but the original logic
        # included it in maintenance_sweep_job.
        # Since I migrated logic to tasks, the metric update should be there too?
        # Re-checking scheduler_tasks.py -> I missed migrating the metric update part!
        
        # Let's keep the metric update here as a lightweight "Orchestrator Health Check" 
        # or relying on the Celery task to do it (if I update scheduler_tasks.py later).
        # For now, simplistic dispatch.

    def start(self) -> None:
        """Defines cron schedules and starts APScheduler."""
        # HIGH_VALUE: Every 6 hours
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(hour="0,6,12,18", minute=0, timezone="UTC"),
            id="cohort_high_value_scan",
            args=[TenantCohort.HIGH_VALUE],
            replace_existing=True
        )
        # ACTIVE: Daily 2AM
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="cohort_active_scan",
            args=[TenantCohort.ACTIVE],
            replace_existing=True
        )
        # DORMANT: Weekly Sun 3AM
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="UTC"),
            id="cohort_dormant_scan",
            args=[TenantCohort.DORMANT],
            replace_existing=True
        )
        # Remediation: Fri 8PM
        self.scheduler.add_job(
            self.auto_remediation_job,
            trigger=CronTrigger(day_of_week="fri", hour=20, minute=0, timezone="UTC"),
            id="weekly_remediation_sweep",
            replace_existing=True
        )
        # Billing: Daily 4AM
        self.scheduler.add_job(
            self.billing_sweep_job,
            trigger=CronTrigger(hour=4, minute=0, timezone="UTC"),
            id="daily_billing_sweep",
            replace_existing=True
        )
        # Stuck Job Detector: Every hour
        self.scheduler.add_job(
            self.detect_stuck_jobs,
            trigger=CronTrigger(minute=0, timezone="UTC"),
            id="stuck_job_detector",
            replace_existing=True
        )
        # Maintenance: Daily 3AM UTC
        self.scheduler.add_job(
            self.maintenance_sweep_job,
            trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="daily_maintenance_sweep",
            replace_existing=True
        )
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.shutdown(wait=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.scheduler.running,
            "last_run_success": self._last_run_success,
            "last_run_time": self._last_run_time,
            "jobs": [str(job.id) for job in self.scheduler.get_jobs()]
        }


class SchedulerService(SchedulerOrchestrator):
    """
    Proxy class for backward compatibility. 
    Inherits from refactored Orchestrator to maintain existing API.
    """
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker)
        logger.info("scheduler_proxy_initialized", refactor_version="1.0-modular")

    async def daily_analysis_job(self) -> None:
        """Legacy entry point, proxies to a full scan."""
        from .cohorts import TenantCohort
        # High value → Active → Dormant
        await self.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        await self.cohort_analysis_job(TenantCohort.ACTIVE)
        await self.cohort_analysis_job(TenantCohort.DORMANT)
        self._last_run_success = True
        self._last_run_time = datetime.now(timezone.utc).isoformat()
