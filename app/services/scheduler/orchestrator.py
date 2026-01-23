from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date, timedelta, datetime, timezone
import asyncio
import time
import structlog
from app.services.scheduler.metrics import SCHEDULER_JOB_RUNS, SCHEDULER_JOB_DURATION
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


# Metrics are now imported from app.services.scheduler.metrics

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
        """
        PRODUCTION: Atomically enqueue jobs for all tenants in a cohort.
        Uses SKIP LOCKED and exponential backoff for deadlock resilience.
        """
        import uuid
        from app.models.background_job import BackgroundJob, JobStatus, JobType
        from sqlalchemy.dialects.postgresql import insert
        from app.services.scheduler.metrics import (
            SCHEDULER_DEADLOCK_DETECTED,
            BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED
        )
        
        job_id = str(uuid.uuid4())
        set_correlation_id(job_id)
        structlog.contextvars.bind_contextvars(
            correlation_id=job_id, 
            job_type="scheduler_cohort", 
            cohort=target_cohort.value
        )
        
        job_name = f"cohort_{target_cohort.value.lower()}_enqueue"
        start_time = time.time()
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with self.session_maker() as db:
                    async with db.begin():
                        # 1. Fetch tenants with row-level lock (SKIP LOCKED prevents deadlocks)
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
                            self._last_run_success = True
                            self._last_run_time = datetime.now(timezone.utc).isoformat()
                            return

                        # 2. Generate deterministic dedup keys
                        now = datetime.now(timezone.utc)
                        bucket = now.replace(minute=0, second=0, microsecond=0)
                        if target_cohort == TenantCohort.HIGH_VALUE:
                            # 6-hourly buckets for high-value
                            hour = (now.hour // 6) * 6
                            bucket = bucket.replace(hour=hour)
                        elif target_cohort == TenantCohort.ACTIVE:
                            # 3-hourly buckets for active
                            hour = (now.hour // 3) * 3
                            bucket = bucket.replace(hour=hour)
                        
                        bucket_str = bucket.isoformat()
                        jobs_enqueued = 0

                        # 3. Insert and Track
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
                                
                                result_proxy = await db.execute(stmt)
                                if result_proxy.rowcount > 0:
                                    jobs_enqueued += 1
                                    BACKGROUND_JOBS_ENQUEUED.labels(
                                        job_type=jtype.value, 
                                        cohort=target_cohort.value
                                    ).inc()
                        
                        logger.info("cohort_scan_enqueued", 
                                   cohort=target_cohort.value, 
                                   tenants=len(cohort_tenants),
                                   jobs_enqueued=jobs_enqueued)
                        
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
                self._last_run_success = True
                self._last_run_time = datetime.now(timezone.utc).isoformat()
                break # Success exit

            except Exception as e:
                retry_count += 1
                if "deadlock" in str(e).lower() or "concurrent" in str(e).lower():
                    SCHEDULER_DEADLOCK_DETECTED.labels(cohort=target_cohort.value).inc()
                    if retry_count < max_retries:
                        backoff = 2 ** (retry_count - 1)
                        logger.warning("scheduler_deadlock_retry", cohort=target_cohort.value, attempt=retry_count, backoff=backoff)
                        await asyncio.sleep(backoff)
                        continue
                
                logger.error("scheduler_cohort_enqueue_failed", job=job_name, error=str(e), attempt=retry_count)
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
                self._last_run_success = False
                self._last_run_time = datetime.now(timezone.utc).isoformat()
                break
        
        duration = time.time() - start_time
        SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

    async def _is_low_carbon_window(self, region: str) -> bool:
        """
        Determines if current time is a 'Green Window' for this region.
        In production, this would call an API like Electricity Maps.
        """
        now = datetime.now(timezone.utc)
        hour = now.hour
        is_green = (10 <= hour <= 16) or (0 <= hour <= 5)
        logger.info("carbon_window_check", region=region, hour=hour, is_green=is_green)
        return is_green

    async def auto_remediation_job(self):
        """Weekly autonomous remediation sweep using hardened retry logic."""
        import uuid
        from app.models.background_job import BackgroundJob, JobType, JobStatus
        from sqlalchemy.dialects.postgresql import insert
        from app.services.scheduler.metrics import (
            SCHEDULER_DEADLOCK_DETECTED,
            BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED
        )
        
        job_id = str(uuid.uuid4())
        set_correlation_id(job_id)
        job_name = "weekly_remediation_sweep"
        start_time = time.time()
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with self.session_maker() as db:
                    async with db.begin():
                        result = await db.execute(
                            sa.select(AWSConnection).with_for_update(skip_locked=True)
                        )
                        connections = result.scalars().all()
                        
                        now = datetime.now(timezone.utc)
                        bucket_str = now.strftime("%Y-W%U")
                        jobs_enqueued = 0

                        for conn in connections:
                            is_green = await self._is_low_carbon_window(conn.region)
                            scheduled_time = now
                            if not is_green:
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
                            
                            result_proxy = await db.execute(stmt)
                            if result_proxy.rowcount > 0:
                                jobs_enqueued += 1
                                BACKGROUND_JOBS_ENQUEUED.labels(
                                    job_type=JobType.REMEDIATION.value, 
                                    cohort="REMEDIATION"
                                ).inc()
                        
                        logger.info("auto_remediation_sweep_completed", count=len(connections), jobs_enqueued=jobs_enqueued)
                
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
                break
            except Exception as e:
                retry_count += 1
                if "deadlock" in str(e).lower() or "concurrent" in str(e).lower():
                    SCHEDULER_DEADLOCK_DETECTED.labels(cohort="REMEDIATION").inc()
                    if retry_count < max_retries:
                        await asyncio.sleep(2 ** (retry_count - 1))
                        continue
                logger.error("auto_remediation_sweep_failed", error=str(e), attempt=retry_count)
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
                break
        
        duration = time.time() - start_time
        SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

    async def billing_sweep_job(self):
        """Daily sweep to find subscriptions due renewal with hardened retry logic."""
        from app.services.billing.paystack_billing import TenantSubscription, SubscriptionStatus
        from app.models.background_job import BackgroundJob, JobType, JobStatus
        from sqlalchemy.dialects.postgresql import insert
        from app.services.scheduler.metrics import (
            SCHEDULER_DEADLOCK_DETECTED,
            BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED
        )
        
        job_name = "daily_billing_sweep"
        start_time = time.time()
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with self.session_maker() as db:
                    async with db.begin():
                        query = sa.select(TenantSubscription).where(
                            TenantSubscription.status == SubscriptionStatus.ACTIVE.value,
                            TenantSubscription.next_payment_date <= datetime.now(timezone.utc),
                            TenantSubscription.paystack_auth_code.isnot(None)
                        ).with_for_update(skip_locked=True)
                        
                        result = await db.execute(query)
                        due_subscriptions = result.scalars().all()

                        now = datetime.now(timezone.utc)
                        bucket_str = now.strftime("%Y-%m-%d")
                        jobs_enqueued = 0

                        for sub in due_subscriptions:
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
                            
                            result_proxy = await db.execute(stmt)
                            if result_proxy.rowcount > 0:
                                jobs_enqueued += 1
                                BACKGROUND_JOBS_ENQUEUED.labels(
                                    job_type=JobType.RECURRING_BILLING.value, 
                                    cohort="BILLING"
                                ).inc()
                        
                        logger.info("billing_sweep_completed", due_count=len(due_subscriptions), jobs_enqueued=jobs_enqueued)
                
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
                break
            except Exception as e:
                retry_count += 1
                if "deadlock" in str(e).lower() or "concurrent" in str(e).lower():
                    SCHEDULER_DEADLOCK_DETECTED.labels(cohort="BILLING").inc()
                    if retry_count < max_retries:
                        await asyncio.sleep(2 ** (retry_count - 1))
                        continue
                logger.error("billing_sweep_failed", error=str(e), attempt=retry_count)
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
                break
        
        duration = time.time() - start_time
        SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)


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

            # 3. Update Pending Jobs Metric (Series-A Observability Audit)
            try:
                from app.core.ops_metrics import BACKGROUND_JOBS_PENDING
                from app.models.background_job import BackgroundJob, JobStatus, JobType
                # Count pending/scheduled jobs by type
                stmt = sa.select(
                    BackgroundJob.job_type,
                    sa.func.count(BackgroundJob.id)
                ).where(
                    BackgroundJob.status.in_([JobStatus.PENDING, JobStatus.SCHEDULED]),
                    BackgroundJob.is_deleted == False
                ).group_by(BackgroundJob.job_type)
                
                counts = await db.execute(stmt)
                for jtype, count in counts:
                    BACKGROUND_JOBS_PENDING.labels(job_type=jtype).set(count)
                logger.info("ops_metrics_jobs_pending_updated")
            except Exception as e:
                logger.warning("ops_metrics_jobs_pending_update_failed", error=str(e))

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
