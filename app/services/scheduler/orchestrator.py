from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date, timedelta, datetime, timezone
import asyncio
import time
import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.models.tenant import Tenant
from app.models.aws_connection import AWSConnection
from app.core.tracing import set_correlation_id
from app.services.scheduler.cohorts import TenantCohort, get_tenant_cohort
from app.services.scheduler.processors import AnalysisProcessor

logger = structlog.get_logger()

# Prometheus Metrics
SCHEDULER_JOB_RUNS = Counter(
    "valdrix_scheduler_job_runs_total",
    "Total number of scheduled job runs",
    ["job_name", "status"]
)

SCHEDULER_JOB_DURATION = Histogram(
    "valdrix_scheduler_job_duration_seconds",
    "Duration of scheduled jobs in seconds",
    ["job_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

class SchedulerOrchestrator:
    """Manages APScheduler and job distribution."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.scheduler = AsyncIOScheduler()
        self.session_maker = session_maker
        self.processor = AnalysisProcessor()
        self.semaphore = asyncio.Semaphore(10)
        self._last_run_success: bool | None = None
        self._last_run_time: str | None = None

    async def cohort_analysis_job(self, target_cohort: TenantCohort):
        """Enqueues analysis jobs for all tenants in a specific cohort."""
        job_id = set_correlation_id()
        structlog.contextvars.bind_contextvars(correlation_id=job_id, job_type="scheduling", cohort=target_cohort.value)
        
        job_name = f"cohort_{target_cohort.value}_enqueue"
        start_time = time.time()
        logger.info("scheduler_cohort_enqueue_starting", job=job_name, cohort=target_cohort.value)

        try:
            async with self.session_maker() as db:
                # SQL-level Cohort Filtering (Optimization from Principal Audit)
                # Instead of fetching ALL and filtering in Python, we filter in DB.
                query = select(Tenant)
                
                if target_cohort == TenantCohort.HIGH_VALUE:
                    query = query.where(Tenant.plan.in_(["enterprise", "pro"]))
                elif target_cohort == TenantCohort.ACTIVE:
                    query = query.where(Tenant.plan == "growth")
                else: # DORMANT
                    query = query.where(Tenant.plan.in_(["starter", "trial"]))

                result = await db.execute(query)
                cohort_tenants = result.scalars().all()

                if not cohort_tenants:
                    logger.info("scheduler_cohort_empty", cohort=target_cohort.value)
                    return

                from app.services.jobs.processor import enqueue_job
                from app.models.background_job import JobType

                enqueue_tasks = []
                for tenant in cohort_tenants:
                    # Enqueue Analysis Job
                    enqueue_tasks.append(enqueue_job(
                        db=db,
                        job_type=JobType.FINOPS_ANALYSIS,
                        tenant_id=tenant.id,
                        payload={"cohort": target_cohort.value}
                    ))
                    # Enqueue Zombie Scan Job
                    enqueue_tasks.append(enqueue_job(
                        db=db,
                        job_type=JobType.ZOMBIE_SCAN,
                        tenant_id=tenant.id,
                        payload={"cohort": target_cohort.value}
                    ))
                    # Enqueue Cost Ingestion Job (New in Phase 11)
                    enqueue_tasks.append(enqueue_job(
                        db=db,
                        job_type=JobType.COST_INGESTION,
                        tenant_id=tenant.id,
                        payload={"cohort": target_cohort.value}
                    ))

                await asyncio.gather(*enqueue_tasks)
                await db.commit()

            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            self._last_run_success = True
            self._last_run_time = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error("scheduler_cohort_enqueue_failed", job=job_name, error=str(e))
            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            self._last_run_success = False
            self._last_run_time = datetime.now(timezone.utc).isoformat()
        finally:
            duration = time.time() - start_time
            SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

    async def auto_remediation_job(self):
        """Weekly autonomous remediation sweep (Enqueues jobs)."""
        job_id = set_correlation_id()
        structlog.contextvars.bind_contextvars(correlation_id=job_id, job_type="scheduling_remediation")
        
        async with self.session_maker() as db:
            result = await db.execute(select(AWSConnection))
            connections = result.scalars().all()

            from app.services.jobs.processor import enqueue_job
            from app.models.background_job import JobType

            enqueue_tasks = [
                enqueue_job(
                    db=db,
                    job_type=JobType.REMEDIATION,
                    tenant_id=conn.tenant_id,
                    payload={"connection_id": str(conn.id), "region": conn.region}
                ) for conn in connections
            ]
            await asyncio.gather(*enqueue_tasks)
            await db.commit()

    def start(self):
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
        self.scheduler.start()

    def stop(self):
        self.scheduler.shutdown(wait=True)

    def get_status(self) -> dict:
        return {
            "running": self.scheduler.running,
            "last_run_success": self._last_run_success,
            "last_run_time": self._last_run_time,
            "jobs": [job.id for job in self.scheduler.get_jobs()]
        }
