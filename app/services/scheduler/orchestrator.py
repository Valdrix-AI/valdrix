from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date, timedelta, datetime, timezone
import asyncio
import time
import structlog
from prometheus_client import Counter, Histogram
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.tenant import Tenant

from app.models.aws_connection import AWSConnection
from app.core.tracing import set_correlation_id
from app.services.scheduler.cohorts import TenantCohort, get_tenant_cohort
from app.services.scheduler.processors import AnalysisProcessor

logger = structlog.get_logger()

# Arbitrary constant for scheduler advisory locks - DEPRECATED in favor of SELECT FOR UPDATE
# Keeping for reference of lock inheritance
SCHEDULER_LOCK_BASE_ID = 48293021


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
        import uuid
        job_id = str(uuid.uuid4())
        set_correlation_id(job_id)
        structlog.contextvars.bind_contextvars(correlation_id=job_id, job_type="scheduling", cohort=target_cohort.value)
        
        job_name = f"cohort_{target_cohort.value}_enqueue"
        start_time = time.time()

        try:
            async with self.session_maker() as db:
                async with db.begin():
                    # SQL-level Cohort Filtering with Row-level Locking (BE-SCHED-1)
                    # Use SELECT FOR UPDATE SKIP LOCKED to prevent duplicate enqueuing across nodes
                    query = sa.select(Tenant).with_for_update(skip_locked=True)
                    
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

            # BE-SCHED-1: Move insertions outside the main transaction to prevent deadlocks
            # BE-SCHED-6: Generate deterministic deduplication keys (tenant_id:job_type:bucket)
            # Use 6-hour buckets for cohort scans
            now = datetime.now(timezone.utc)
            bucket = now.replace(minute=0, second=0, microsecond=0)
            if target_cohort == TenantCohort.HIGH_VALUE:
                # Bucket every 6 hours
                hour = (now.hour // 6) * 6
                bucket = bucket.replace(hour=hour)
            
            bucket_str = bucket.isoformat()
            
            async with self.session_maker() as db:
                from app.models.background_job import BackgroundJob, JobStatus, JobType
                from sqlalchemy.dialects.postgresql import insert
                
                for tenant in cohort_tenants:
                    for jtype in [JobType.FINOPS_ANALYSIS, JobType.ZOMBIE_SCAN, JobType.COST_INGESTION]:
                        dedup_key = f"{tenant.id}:{jtype.value}:{bucket_str}"
                        stmt = insert(BackgroundJob).values(
                            job_type=jtype.value,
                            tenant_id=tenant.id,
                            status=JobStatus.PENDING,
                            scheduled_for=now,
                            created_at=now,
                            deduplication_key=dedup_key
                        ).on_conflict_do_nothing(index_elements=["deduplication_key"])
                        await db.execute(stmt)
                        
                        # Track in Prometheus (Phase 2)
                        BACKGROUND_JOBS_ENQUEUED.labels(job_type=jtype.value, priority=0).inc()
                    
                await db.commit()
                logger.info("cohort_scan_enqueued", cohort=target_cohort.value, tenants=len(cohort_tenants))

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

    async def _is_low_carbon_window(self, region: str) -> bool:
        """
        Determines if current time is a 'Green Window' for this region.
        In production, this would call an API like Electricity Maps.
        For now, we use a deterministic mock based on hour of day (assuming 
        solar/wind peaks or night-time low demand).
        """
        now = datetime.now(timezone.utc)
        # Mock: 10AM - 4PM UTC is high solar, thus "Green"
        # 12AM - 5AM UTC is low demand, also "Green"
        hour = now.hour
        is_green = (10 <= hour <= 16) or (0 <= hour <= 5)
        
        logger.info("carbon_window_check", region=region, hour=hour, is_green=is_green)
        return is_green

    async def auto_remediation_job(self):
        """Weekly autonomous remediation sweep (Enqueues jobs)."""
        import uuid
        job_id = str(uuid.uuid4())
        set_correlation_id(job_id)
        
        async with self.session_maker() as db:
            async with db.begin():
                # Advisory locks are fragile; use row-level locking for atomic job creation (BE-SCHED-1)
                result = await db.execute(
                    sa.select(AWSConnection)
                    .with_for_update(skip_locked=True)
                )
                connections = result.scalars().all()

                from app.models.background_job import BackgroundJob, JobType, JobStatus
                from sqlalchemy.dialects.postgresql import insert
                from app.core.ops_metrics import BACKGROUND_JOBS_ENQUEUED
                
                now = datetime.now(timezone.utc)
                # Week-based bucket for remediation
                bucket_str = now.strftime("%Y-W%U")

                for conn in connections:
                    # GreenOps 2.0: Check if we should delay for carbon efficiency
                    is_green = await self._is_low_carbon_window(conn.region)
                    scheduled_time = now
                    
                    if not is_green:
                        # Delay to next green window (e.g., 4 hours later)
                        scheduled_time += timedelta(hours=4)

                    dedup_key = f"{conn.tenant_id}:{JobType.REMEDIATION.value}:{bucket_str}"
                    stmt = insert(BackgroundJob).values(
                        job_type=JobType.REMEDIATION.value,
                        tenant_id=conn.tenant_id,
                        payload={"connection_id": str(conn.id), "region": conn.region},
                        status=JobStatus.PENDING,
                        scheduled_for=scheduled_time,
                        created_at=now,
                        deduplication_key=dedup_key
                    ).on_conflict_do_nothing(index_elements=["deduplication_key"])
                    await db.execute(stmt)
                    
                    # Track in Prometheus (Phase 2)
                    BACKGROUND_JOBS_ENQUEUED.labels(job_type=JobType.REMEDIATION.value, priority=1).inc()
                
                await db.commit()
                logger.info("auto_remediation_sweep_completed", connections=len(connections))

    async def billing_sweep_job(self):
        """Daily sweep to find subscriptions due for renewal."""
        from app.services.billing.paystack_billing import TenantSubscription, SubscriptionStatus
        from app.models.background_job import BackgroundJob, JobType, JobStatus
        
        async with self.session_maker() as db:
            async with db.begin():
                # Find active subscriptions where next_payment_date is in the past
                # SEC: Use SKIP LOCKED to avoid double-billing (BE-SCHED-1)
                query = sa.select(TenantSubscription).where(
                    TenantSubscription.status == SubscriptionStatus.ACTIVE.value,
                    TenantSubscription.next_payment_date <= datetime.now(timezone.utc),
                    TenantSubscription.paystack_auth_code.isnot(None)
                ).with_for_update(skip_locked=True)
                
                result = await db.execute(query)
                due_subscriptions = result.scalars().all()

                from sqlalchemy.dialects.postgresql import insert
                now = datetime.now(timezone.utc)
                bucket_str = now.strftime("%Y-%m-%d")

                for sub in due_subscriptions:
                    # Enqueue individual renewal job
                    dedup_key = f"{sub.tenant_id}:{JobType.RECURRING_BILLING.value}:{bucket_str}"
                    stmt = insert(BackgroundJob).values(
                        job_type=JobType.RECURRING_BILLING.value,
                        tenant_id=sub.tenant_id,
                        payload={"subscription_id": str(sub.id)},
                        status=JobStatus.PENDING,
                        scheduled_for=now,
                        created_at=now,
                        deduplication_key=dedup_key
                    ).on_conflict_do_nothing(index_elements=["deduplication_key"])
                    await db.execute(stmt)
                    
                    # Track in Prometheus (Phase 2)
                    from app.core.ops_metrics import BACKGROUND_JOBS_ENQUEUED
                    BACKGROUND_JOBS_ENQUEUED.labels(job_type=JobType.RECURRING_BILLING.value, priority=2).inc()
                
                await db.commit()
                
                logger.info("billing_sweep_completed", due_count=len(due_subscriptions))

    async def detect_stuck_jobs(self):
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
                BackgroundJob.is_deleted == False
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

    async def maintenance_sweep_job(self):
        """
        Daily infrastructure maintenance task.
        - Finalizes PRELIMINARY cost records after 48-hour restatement window (BE-FIN-RECON-1).
        - Refreshes cost aggregation materialized view (Phase 4.3).
        - Archives old partitions (Phase 4.4).
        """
        from app.services.costs.aggregator import CostAggregator
        from app.services.costs.persistence import CostPersistenceService
        from sqlalchemy import text
        
        async with self.session_maker() as db:
            # 0. Finalize cost records older than 48 hours (BE-FIN-RECON-1)
            logger.info("maintenance_cost_finalization_start")
            try:
                persistence = CostPersistenceService(db)
                result = await persistence.finalize_batch(days_ago=2)
                logger.info("maintenance_cost_finalization_success", 
                           records_finalized=result.get("records_finalized", 0))
            except Exception as e:
                logger.warning("maintenance_cost_finalization_failed", error=str(e))
            
            # 1. Refresh Caching View
            logger.info("maintenance_refresh_view_start")
            success = await CostAggregator.refresh_materialized_view(db)
            if success:
                logger.info("maintenance_refresh_view_success")
            
            # 2. Archive Old Partitions
            logger.info("maintenance_archival_start")
            try:
                # Call the PL/pgSQL function created in the migration/script
                await db.execute(text("SELECT archive_old_cost_partitions();"))
                await db.commit()
                logger.info("maintenance_archival_success")
            except Exception as e:
                logger.warning("maintenance_archival_failed", error=str(e))
                # Function might not exist yet if script-based creation failed
                pass

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

    def stop(self):
        self.scheduler.shutdown(wait=True)

    def get_status(self) -> dict:
        return {
            "running": self.scheduler.running,
            "last_run_success": self._last_run_success,
            "last_run_time": self._last_run_time,
            "jobs": [job.id for job in self.scheduler.get_jobs()]
        }


class SchedulerService(SchedulerOrchestrator):
    """
    Proxy class for backward compatibility. 
    Inherits from refactored Orchestrator to maintain existing API.
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker)
        logger.info("scheduler_proxy_initialized", refactor_version="1.0-modular")

    async def daily_analysis_job(self):
        """Legacy entry point, proxies to a full scan."""
        from .cohorts import TenantCohort
        # High value → Active → Dormant
        await self.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        await self.cohort_analysis_job(TenantCohort.ACTIVE)
        await self.cohort_analysis_job(TenantCohort.DORMANT)
        self._last_run_success = True
        self._last_run_time = datetime.now(timezone.utc).isoformat()
