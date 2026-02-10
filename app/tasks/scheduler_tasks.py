import asyncio
from typing import Any
import structlog
from celery import shared_task
from app.shared.db.session import async_session_maker
from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.modules.governance.domain.scheduler.orchestrator import SchedulerOrchestrator
from app.shared.core.currency import get_exchange_rate
from app.modules.reporting.domain.aggregator import CostAggregator
from app.modules.reporting.domain.persistence import CostPersistenceService
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
from contextlib import asynccontextmanager
import inspect

logger = structlog.get_logger()


@asynccontextmanager
async def _open_db_session():
    """Robust helper to obtain an async DB session from `async_session_maker`.

    This handles several shapes that tests/mocks may provide:
    - a callable that returns an async context manager
    - an AsyncMock/coroutine that resolves to a context manager
    - a context manager instance directly
    """
    maker_result = async_session_maker()
    # If the factory returned an awaitable that is NOT itself an async
    # context manager (e.g. AsyncMock used as coroutine), await it.
    if (asyncio.iscoroutine(maker_result) or inspect.isawaitable(maker_result)) and not hasattr(maker_result, "__aenter__"):
        maker_result = await maker_result

    # Try entering as an async context manager
    try:
        async with maker_result as session:
            # If session is awaitable but not an async context manager, await it
            if (asyncio.iscoroutine(session) or inspect.isawaitable(session)) and not hasattr(session, "__aenter__"):
                session = await session
            yield session
            return
    except TypeError:
        # Not an async context manager; maybe it's the session object itself
        session = maker_result
        if (asyncio.iscoroutine(session) or inspect.isawaitable(session)) and not hasattr(session, "__aenter__"):
            session = await session
        yield session
        return
# Helper to run async code in sync Celery task
def run_async(task_or_coro: Any, *args: Any, func: Any = None, **kwargs: Any) -> Any:
    """
    Run an async callable/coroutine from sync code.

    Supported call patterns:
    - run_async(coroutine)
    - run_async(callable, *args, **kwargs)
    - run_async(cohort_value, func=_cohort_analysis_logic)  # testing-friendly
    """
    # If caller provided a helper `func` and the first arg is not awaitable/callable,
    # treat the first positional as a parameter to `func` (used by tests).
    if func is not None and not asyncio.iscoroutine(task_or_coro) and not callable(task_or_coro):
        return asyncio.run(func(task_or_coro, *args, **kwargs))

    # If given an awaitable/coroutine object
    if asyncio.iscoroutine(task_or_coro) or inspect.isawaitable(task_or_coro):
        return asyncio.run(task_or_coro)

    # If given a callable coroutine/function
    if callable(task_or_coro):
        return asyncio.run(task_or_coro(*args, **kwargs))

    # Fallback: try to run it as-is
    return asyncio.run(task_or_coro)

@shared_task(name="scheduler.cohort_analysis")
def run_cohort_analysis(cohort_value: str) -> None:
    """
    Celery task to enqueue jobs for a tenant cohort.
    Wraps async logic in synchronous execution.
    """
    # Accept either the enum member, the enum name (str) or the enum value
    if isinstance(cohort_value, TenantCohort):
        cohort = cohort_value
    else:
        try:
            # Try lookup by member name first (e.g. "HIGH_VALUE")
            cohort = TenantCohort[cohort_value]
        except Exception:
            # Fallback to value-based construction (for numeric or other values)
            cohort = TenantCohort(cohort_value)

    # Call run_async in a test-friendly way: pass the cohort as the first
    # positional arg while providing the logic via `func` so patched
    # `run_async` can inspect the cohort argument.
    run_async(cohort, func=_cohort_analysis_logic)

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
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
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
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
                    result = await db.execute(
                        sa.select(AWSConnection).with_for_update(skip_locked=True)
                    )
                    connections = result.scalars().all()
                    
                    now = datetime.now(timezone.utc)
                    bucket_str = now.strftime("%Y-W%U")
                    jobs_enqueued = 0
                    orchestrator = SchedulerOrchestrator(async_session_maker)

                    for conn in connections:
                        # Unified green window logic (H-2: Deduplicated scheduling logic)
                        is_green = await orchestrator.is_low_carbon_window(conn.region)
                        
                        scheduled_time = now
                        if not is_green:
                            scheduled_time += timedelta(hours=4)

                        dedup_key = f"{conn.tenant_id}:{conn.id}:{JobType.REMEDIATION.value}:{bucket_str}"
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
        async with _open_db_session() as db:
            begin_ctx = db.begin()
            if (asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)) and not hasattr(begin_ctx, "__aenter__"):
                begin_ctx = await begin_ctx
            async with begin_ctx:
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
    from sqlalchemy import text
    
    async with _open_db_session() as db:
        # 0. Finalize cost records
        try:
            persistence = CostPersistenceService(db)
            result = await persistence.finalize_batch(days_ago=2)
            logger.info("maintenance_cost_finalization_success", records=result.get("records_finalized", 0))
        except Exception as e:
            logger.warning("maintenance_cost_finalization_failed", error=str(e))
        
        # 1. Refresh View
        aggregator = CostAggregator()
        await aggregator.refresh_materialized_view(db)
        
        # 2. Archive
        try:
            await db.execute(text("SELECT archive_old_cost_partitions();"))
            await db.commit()
        except Exception as e:
            logger.error("maintenance_archive_failed", error=str(e))
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

@shared_task(name="scheduler.daily_finops_scan")
def daily_finops_scan() -> None:
    """
    Central orchestration task that triggers analysis for all tenant cohorts.
    Runs daily (usually at 00:00 UTC).
    """
    logger.info("daily_finops_scan_started")
    start_time = time.time()
    successful_dispatches = 0
    failed_dispatches = 0

    # Iterate through all defined cohorts
    for cohort in TenantCohort:
        try:
            # Trigger analysis for this cohort
            # We use .delay() to enqueue the job asynchronously in Celery
            run_cohort_analysis.delay(cohort.value)
            successful_dispatches += 1
            logger.info("cohort_analysis_dispatched", cohort=cohort.value)
        except Exception as e:
            failed_dispatches += 1
            logger.error(
                "daily_finops_scan_partial_failure", 
                cohort=cohort.value, 
                error=str(e)
            )

    duration = time.time() - start_time
    logger.info(
        "daily_finops_scan_completed",
        duration_seconds=duration,
        successful=successful_dispatches,
        failed=failed_dispatches
    )
