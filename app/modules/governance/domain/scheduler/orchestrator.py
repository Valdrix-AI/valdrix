from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timezone
import asyncio
import time
import os
import structlog
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from typing import Dict, Any
import httpx

from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.modules.governance.domain.scheduler.processors import AnalysisProcessor
from app.shared.core.config import get_settings
from app.shared.core.rate_limit import get_redis_client
from app.shared.core.ops_metrics import STUCK_JOB_COUNT

logger = structlog.get_logger()
settings = get_settings()

# Arbitrary constant for scheduler advisory locks - DEPRECATED in favor of SELECT FOR UPDATE
# Keeping for reference of lock inheritance
SCHEDULER_LOCK_BASE_ID = 48293021


# Metrics are now imported from app.modules.governance.domain.scheduler.metrics


class SchedulerOrchestrator:
    """Manages APScheduler and job distribution."""

    REGION_TO_ELECTRICITYMAP_ZONE = {
        "us-east-1": "US-MIDA-PJM",
        "us-west-2": "US-NW-BPAT",
        "eu-west-1": "IE",
        "eu-central-1": "DE",
        "ap-southeast-1": "SG",
        "ap-northeast-1": "JP-TK",
    }

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.scheduler = AsyncIOScheduler()
        self.session_maker = session_maker
        self.processor = AnalysisProcessor()
        self.semaphore = asyncio.Semaphore(10)
        self._last_run_success: bool | None = None
        self._last_run_time: str | None = None
        self._carbon_cache: dict[str, tuple[float, float]] = {}

    async def _acquire_dispatch_lock(
        self, job_name: str, ttl_seconds: int = 180
    ) -> bool:
        """
        Acquire a distributed dispatch lock to prevent duplicate schedule dispatches
        when multiple API instances are running APScheduler.
        """
        # Test runs should be deterministic and fast; do not depend on Redis lock timing.
        if settings.TESTING or os.getenv("PYTEST_CURRENT_TEST"):
            return True

        redis = get_redis_client()
        if redis is None:
            return True

        lock_key = f"scheduler:dispatch-lock:{job_name}"
        try:
            acquired = await redis.set(lock_key, "1", ex=ttl_seconds, nx=True)
            if not acquired:
                logger.info("scheduler_dispatch_skipped_lock_held", job=job_name)
                return False
            return True
        except Exception as exc:
            # Fail-open: if lock infrastructure fails, keep scheduler functional.
            logger.warning(
                "scheduler_dispatch_lock_error", job=job_name, error=str(exc)
            )
            return True

    async def cohort_analysis_job(self, target_cohort: TenantCohort) -> None:
        """
        PRODUCTION: Enqueues a distributed task for cohort analysis.
        """
        logger.info("scheduler_dispatching_cohort_job", cohort=target_cohort.value)
        if not await self._acquire_dispatch_lock(f"cohort:{target_cohort.value}"):
            return

        # Skip Celery dispatch if Redis unavailable (local dev)
        try:
            from app.shared.core.celery_app import celery_app

            celery_app.send_task(
                "scheduler.cohort_analysis", args=[target_cohort.value]
            )
        except Exception as e:
            logger.warning(
                "scheduler_celery_unavailable", error=str(e), cohort=target_cohort.value
            )

        self._last_run_success = True
        self._last_run_time = datetime.now(timezone.utc).isoformat()

    async def is_low_carbon_window(self, region: str = "us-east-1") -> bool:
        """
        Series-A (Phase 4): Carbon-Aware Scheduling.
        Returns True if the current time is a 'Green Window' for the region.

        Logic:
        - 10 AM to 4 PM (10:00 - 16:00) usually has high solar output.
        - 12 AM to 5 AM (00:00 - 05:00) usually has low grid demand.
        """
        live_intensity = await self._fetch_live_carbon_intensity(region)
        if live_intensity is not None:
            is_green = live_intensity <= settings.CARBON_LOW_INTENSITY_THRESHOLD
            logger.info(
                "scheduler_green_window_check_live",
                region=region,
                live_intensity=live_intensity,
                threshold=settings.CARBON_LOW_INTENSITY_THRESHOLD,
                is_green=is_green,
            )
            return is_green

        now = datetime.now(timezone.utc)
        hour = now.hour
        # Fallback heuristic when live carbon data is unavailable.
        is_green = (10 <= hour <= 16) or (0 <= hour <= 5)
        logger.info(
            "scheduler_green_window_check_fallback",
            hour=hour,
            is_green=is_green,
            region=region,
        )
        return is_green

    async def _fetch_live_carbon_intensity(self, region: str) -> float | None:
        api_key = settings.ELECTRICITY_MAPS_API_KEY
        if not api_key:
            return None

        zone = self.REGION_TO_ELECTRICITYMAP_ZONE.get(region)
        if not zone:
            return None

        now = time.time()
        cached = self._carbon_cache.get(region)
        if cached and (now - cached[1]) < 600:
            return cached[0]

        try:
            async with httpx.AsyncClient(
                timeout=settings.CARBON_INTENSITY_API_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(
                    "https://api.electricitymap.org/v3/carbon-intensity/latest",
                    params={"zone": zone},
                    headers={"auth-token": api_key},
                )
                response.raise_for_status()
                payload = response.json()
            intensity = payload.get("carbonIntensity")
            if intensity is None:
                return None
            value = float(intensity)
            self._carbon_cache[region] = (value, now)
            return value
        except Exception as exc:
            logger.warning(
                "live_carbon_intensity_fetch_failed", region=region, error=str(exc)
            )
            return None

    async def auto_remediation_job(self) -> None:
        """Dispatches weekly remediation sweep."""
        logger.info("scheduler_dispatching_remediation_sweep")
        if not await self._acquire_dispatch_lock("remediation_sweep"):
            return
        try:
            from app.shared.core.celery_app import celery_app

            celery_app.send_task("scheduler.remediation_sweep")
        except Exception as e:
            logger.warning(
                "scheduler_celery_unavailable", error=str(e), job="remediation"
            )

    async def billing_sweep_job(self) -> None:
        """Dispatches billing sweep."""
        logger.info("scheduler_dispatching_billing_sweep")
        if not await self._acquire_dispatch_lock("billing_sweep"):
            return
        try:
            from app.shared.core.celery_app import celery_app

            celery_app.send_task("scheduler.billing_sweep")
        except Exception as e:
            logger.warning("scheduler_celery_unavailable", error=str(e), job="billing")

    async def acceptance_sweep_job(self) -> None:
        """Dispatches daily acceptance-suite evidence capture sweep."""
        logger.info("scheduler_dispatching_acceptance_sweep")
        if not await self._acquire_dispatch_lock("acceptance_sweep"):
            return
        try:
            from app.shared.core.celery_app import celery_app

            celery_app.send_task("scheduler.acceptance_sweep")
        except Exception as e:
            logger.warning(
                "scheduler_celery_unavailable", error=str(e), job="acceptance"
            )

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
                sa.not_(BackgroundJob.is_deleted),
            )
            result = await db.execute(stmt)
            stuck_jobs = result.scalars().all()
            STUCK_JOB_COUNT.set(len(stuck_jobs))

            if stuck_jobs:
                logger.critical(
                    "stuck_jobs_detected",
                    count=len(stuck_jobs),
                    job_ids=[str(j.id) for j in stuck_jobs[:10]],
                )

                # Update status to avoid re-detection (policy decision: alert and fail instead of retry).
                for job in stuck_jobs:
                    job.status = JobStatus.FAILED
                    job.error_message = (
                        "Stuck in PENDING for > 1 hour. Terminated by StuckJobDetector."
                    )

                await db.commit()
                logger.info("stuck_jobs_mitigated", count=len(stuck_jobs))

    async def maintenance_sweep_job(self) -> None:
        """Dispatches maintenance sweep."""
        logger.info("scheduler_dispatching_maintenance_sweep")
        if not await self._acquire_dispatch_lock("maintenance_sweep"):
            return
        try:
            from app.shared.core.celery_app import celery_app

            celery_app.send_task("scheduler.maintenance_sweep")
        except Exception as e:
            logger.warning(
                "scheduler_celery_unavailable", error=str(e), job="maintenance"
            )

        # NOTE: Internal metric migration to task is deliberate (resolved Phase 13 uncertainty).

    def start(self) -> None:
        """Defines cron schedules and starts APScheduler."""
        # HIGH_VALUE: Every 6 hours
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(hour="0,6,12,18", minute=0, timezone="UTC"),
            id="cohort_high_value_scan",
            args=[TenantCohort.HIGH_VALUE],
            replace_existing=True,
        )
        # ACTIVE: Daily 2AM
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="cohort_active_scan",
            args=[TenantCohort.ACTIVE],
            replace_existing=True,
        )
        # DORMANT: Weekly Sun 3AM
        self.scheduler.add_job(
            self.cohort_analysis_job,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="UTC"),
            id="cohort_dormant_scan",
            args=[TenantCohort.DORMANT],
            replace_existing=True,
        )
        # Remediation: Fri 8PM
        self.scheduler.add_job(
            self.auto_remediation_job,
            trigger=CronTrigger(day_of_week="fri", hour=20, minute=0, timezone="UTC"),
            id="weekly_remediation_sweep",
            replace_existing=True,
        )
        # Billing: Daily 4AM
        self.scheduler.add_job(
            self.billing_sweep_job,
            trigger=CronTrigger(hour=4, minute=0, timezone="UTC"),
            id="daily_billing_sweep",
            replace_existing=True,
        )
        # Acceptance evidence capture: Daily 5AM UTC
        self.scheduler.add_job(
            self.acceptance_sweep_job,
            trigger=CronTrigger(hour=5, minute=0, timezone="UTC"),
            id="daily_acceptance_sweep",
            replace_existing=True,
        )
        # Stuck Job Detector: Every hour
        self.scheduler.add_job(
            self.detect_stuck_jobs,
            trigger=CronTrigger(minute=0, timezone="UTC"),
            id="stuck_job_detector",
            replace_existing=True,
        )
        # Maintenance: Daily 3AM UTC
        self.scheduler.add_job(
            self.maintenance_sweep_job,
            trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
            id="daily_maintenance_sweep",
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self) -> None:
        if not self.scheduler.running:
            logger.debug("scheduler_stop_skipped_not_running")
            return
        self.scheduler.shutdown(wait=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.scheduler.running,
            "last_run_success": self._last_run_success,
            "last_run_time": self._last_run_time,
            "jobs": [str(job.id) for job in self.scheduler.get_jobs()],
        }


class SchedulerService(SchedulerOrchestrator):
    """
    Proxy class that exposes the scheduler API used by the app and admin routes.
    Inherits orchestration logic from SchedulerOrchestrator.
    """

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(session_maker)
        logger.info("scheduler_proxy_initialized", refactor_version="1.0-modular")

    async def daily_analysis_job(self) -> None:
        """Run the daily full cohort scan sequence."""
        from .cohorts import TenantCohort

        # High value → Active → Dormant
        await self.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        await self.cohort_analysis_job(TenantCohort.ACTIVE)
        await self.cohort_analysis_job(TenantCohort.DORMANT)
        self._last_run_success = True
        self._last_run_time = datetime.now(timezone.utc).isoformat()
