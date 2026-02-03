import asyncio
from typing import Any
import structlog
from celery import shared_task
from app.shared.db.session import async_session_maker
from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from datetime import datetime, timezone, timedelta
import sqlalchemy as sa
from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob, JobStatus, JobType
from sqlalchemy.dialects.postgresql import insert
from app.modules.governance.domain.scheduler.metrics import (
    SCHEDULER_JOB_RUNS, 
    SCHEDULER_JOB_DURATION,
    SCHEDULER_DEADLOCK_DETECTED,
    BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED
)
import time
import uuid

logger = structlog.get_logger()

# Helper to run async code in sync Celery task
def run_async(coro: Any) -> Any:
    return asyncio.run(coro)

@shared_task(name="scheduler.cohort_analysis")
def run_cohort_analysis(cohort_value: str) -> None:
    """
    Celery task to enqueue jobs for a tenant cohort.
    Wraps async logic in synchronous execution.
    """
    cohort = TenantCohort(cohort_value)
    run_async(_cohort_analysis_logic(cohort))

async def _cohort_analysis_logic(target_cohort: TenantCohort) -> None:
    job_id = str(uuid.uuid4())
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
            async with async_session_maker() as db:
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
                        return

                    # 2. Generate deterministic dedup keys
                    now = datetime.now(timezone.utc)
                    bucket = now.replace(minute=0, second=0, microsecond=0)
                    if target_cohort == TenantCohort.HIGH_VALUE:
                        hour = (now.hour // 6) * 6
                        bucket = bucket.replace(hour=hour)
                    elif target_cohort == TenantCohort.ACTIVE:
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
                            # Cast to CursorResult to access rowcount
                            if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
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
            break
    
    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

@shared_task(name="scheduler.remediation_sweep")
def run_remediation_sweep() -> None:
    run_async(_remediation_sweep_logic())

async def _remediation_sweep_logic() -> None:
    from app.models.aws_connection import AWSConnection
    job_name = "weekly_remediation_sweep"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with async_session_maker() as db:
                async with db.begin():
                    result = await db.execute(
                        sa.select(AWSConnection).with_for_update(skip_locked=True)
                    )
                    connections = result.scalars().all()
                    
                    now = datetime.now(timezone.utc)
                    bucket_str = now.strftime("%Y-W%U")
                    jobs_enqueued = 0

                    for conn in connections:
                        # Simple green window logic (mocked here or duplicated)
                        # Re-implementing logic for simplicity as `orchestrator` method is private
                        hour = now.hour
                        is_green = (10 <= hour <= 16) or (0 <= hour <= 5)
                        
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
                        if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
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
            logger.error("auto_remediation_sweep_failed", error=str(e), attempt=retry_count)
            if retry_count == max_retries:
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            else:
                await asyncio.sleep(2 ** (retry_count - 1))

    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

@shared_task(name="scheduler.billing_sweep")
def run_billing_sweep() -> None:
    run_async(_billing_sweep_logic())

async def _billing_sweep_logic() -> None:
    from app.modules.reporting.domain.billing.paystack_billing import TenantSubscription, SubscriptionStatus
    job_name = "daily_billing_sweep"
    start_time = time.time()
    
    try:
        async with async_session_maker() as db:
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
                    if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
                        jobs_enqueued += 1
                        BACKGROUND_JOBS_ENQUEUED.labels(
                            job_type=JobType.RECURRING_BILLING.value, 
                            cohort="BILLING"
                        ).inc()
                
                logger.info("billing_sweep_completed", due_count=len(due_subscriptions), jobs_enqueued=jobs_enqueued)
        SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
    except Exception as e:
        logger.error("billing_sweep_failed", error=str(e))
        SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
    
    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)

@shared_task(name="scheduler.maintenance_sweep")
def run_maintenance_sweep() -> None:
    run_async(_maintenance_sweep_logic())

async def _maintenance_sweep_logic() -> None:
    from app.modules.reporting.domain.aggregator import CostAggregator
    from app.modules.reporting.domain.persistence import CostPersistenceService
    from sqlalchemy import text
    
    async with async_session_maker() as db:
        # 0. Finalize cost records
        try:
            persistence = CostPersistenceService(db)
            result = await persistence.finalize_batch(days_ago=2)
            logger.info("maintenance_cost_finalization_success", records=result.get("records_finalized", 0))
        except Exception as e:
            logger.warning("maintenance_cost_finalization_failed", error=str(e))
        
        # 1. Refresh View
        await CostAggregator.refresh_materialized_view(db)
        
        # 2. Archive
        try:
            await db.execute(text("SELECT archive_old_cost_partitions();"))
            await db.commit()
        except Exception:
            pass
@shared_task(name="scheduler.currency_sync")
def run_currency_sync() -> None:
    """
    Celery task to refresh currency exchange rates.
    """
    from app.shared.core.currency import get_exchange_rate
    # Fetch common currencies to trigger refresh and Redis sync
    for curr in ["NGN", "EUR", "GBP"]:
        run_async(get_exchange_rate(curr))
    logger.info("currency_sync_completed")
