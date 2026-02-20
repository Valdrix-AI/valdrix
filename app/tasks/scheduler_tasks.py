import asyncio
from typing import Any, AsyncGenerator, Coroutine, cast
import structlog
from celery import shared_task
from app.shared.db.session import async_session_maker
from sqlalchemy.ext.asyncio import AsyncSession
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
    BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED,
)
import time
import uuid
from contextlib import asynccontextmanager
import inspect
from uuid import UUID
from app.shared.core.connection_state import (
    is_connection_active,
    resolve_connection_region,
)
from app.shared.core.connection_queries import list_active_connections_all_tenants
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection

logger = structlog.get_logger()


@asynccontextmanager
async def _open_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Open a DB session using the production async session context manager."""
    session_cm = async_session_maker()
    if not hasattr(session_cm, "__aenter__") or not hasattr(session_cm, "__aexit__"):
        raise TypeError(
            "async_session_maker() must return an async context manager for AsyncSession"
        )

    try:
        async with asyncio.timeout(10.0):
            async with session_cm as session:
                yield session
    except asyncio.TimeoutError as exc:
        logger.error("db_session_acquisition_failed", error=str(exc), type="TimeoutError")
        raise


# Helper to run async code in sync Celery task
def run_async(task_or_coro: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Run an async callable/coroutine from sync code.

    Supported call patterns:
    - run_async(coroutine)
    - run_async(callable, *args, **kwargs)
    """
    if asyncio.iscoroutine(task_or_coro) or inspect.isawaitable(task_or_coro):
        return asyncio.run(cast(Coroutine[Any, Any, Any], task_or_coro))

    if callable(task_or_coro):
        return asyncio.run(task_or_coro(*args, **kwargs))

    raise TypeError("run_async expects an awaitable or a callable async function")


@shared_task(
    name="scheduler.cohort_analysis",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 5},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
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

    run_async(_cohort_analysis_logic, cohort)


async def _cohort_analysis_logic(target_cohort: TenantCohort) -> None:
    job_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(
        correlation_id=job_id, job_type="scheduler_cohort", cohort=target_cohort.value
    )

    job_name = f"cohort_{target_cohort.value.lower()}_enqueue"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (
                    asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                ) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
                    # 1. Fetch tenants with row-level lock (SKIP LOCKED prevents deadlocks)
                    query = sa.select(Tenant).with_for_update(skip_locked=True)

                    if target_cohort == TenantCohort.HIGH_VALUE:
                        query = query.where(Tenant.plan.in_(["enterprise", "pro"]))
                    elif target_cohort == TenantCohort.ACTIVE:
                        query = query.where(Tenant.plan == "growth")
                    else:  # DORMANT
                        # Free tier is on-demand to avoid recurring compute cost.
                        query = query.where(Tenant.plan == "starter")

                    result = await db.execute(query)
                    cohort_tenants = result.scalars().all()

                    if not cohort_tenants:
                        logger.info(
                            "scheduler_cohort_empty", cohort=target_cohort.value
                        )
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
                    jobs_to_insert = []

                    # 3. Generate Job Payloads (No DB I/O in this loop)
                    for tenant in cohort_tenants:
                        from app.shared.core.pricing import (
                            FeatureFlag,
                            is_feature_enabled,
                        )

                        tenant_plan = getattr(tenant, "plan", "")
                        job_types = [JobType.ZOMBIE_SCAN]
                        if is_feature_enabled(tenant_plan, FeatureFlag.INGESTION_SLA):
                            job_types.append(JobType.COST_INGESTION)
                        if is_feature_enabled(tenant_plan, FeatureFlag.LLM_ANALYSIS):
                            job_types.append(JobType.FINOPS_ANALYSIS)
                        if is_feature_enabled(
                            tenant_plan, FeatureFlag.ANOMALY_DETECTION
                        ):
                            job_types.append(JobType.COST_ANOMALY_DETECTION)

                        for jtype in job_types:
                            dedup_key = f"{tenant.id}:{jtype.value}:{bucket_str}"
                            jobs_to_insert.append({
                                "job_type": jtype.value,
                                "tenant_id": tenant.id,
                                "status": JobStatus.PENDING,
                                "scheduled_for": now,
                                "created_at": now,
                                "deduplication_key": dedup_key,
                            })

                    # 4. Atomic Bulk Insert
                    jobs_enqueued = 0
                    if jobs_to_insert:
                        # Process in chunks of 500 to avoid too large statements
                        for i in range(0, len(jobs_to_insert), 500):
                            chunk = jobs_to_insert[i:i+500]
                            stmt = (
                                insert(BackgroundJob)
                                .values(chunk)
                                .on_conflict_do_nothing(
                                    index_elements=["deduplication_key"]
                                )
                            )
                            result_proxy = await db.execute(stmt)
                            
                            # Increment metrics for successful inserts
                            if hasattr(result_proxy, "rowcount"):
                                count = result_proxy.rowcount
                                jobs_enqueued += count
                                # Note: Metric labels are constant for the batch
                                # We'll increment the total after the loop for precision
                    
                    # 5. Record Metrics
                    if jobs_enqueued > 0:
                        BACKGROUND_JOBS_ENQUEUED.labels(
                            job_type="cohort_scan",
                            cohort=target_cohort.value,
                        ).inc(jobs_enqueued)

                    logger.info(
                        "cohort_scan_enqueued",
                        cohort=target_cohort.value,
                        tenants=len(cohort_tenants),
                        jobs_enqueued=jobs_enqueued,
                    )

            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            break  # Success exit

        except Exception as e:
            retry_count += 1
            if "deadlock" in str(e).lower() or "concurrent" in str(e).lower():
                SCHEDULER_DEADLOCK_DETECTED.labels(cohort=target_cohort.value).inc()
                if retry_count < max_retries:
                    backoff = 2 ** (retry_count - 1)
                    logger.warning(
                        "scheduler_deadlock_retry",
                        cohort=target_cohort.value,
                        attempt=retry_count,
                        backoff=backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

            logger.error(
                "scheduler_cohort_enqueue_failed",
                job=job_name,
                error=str(e),
                attempt=retry_count,
            )
            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            break

    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)


@shared_task(
    name="scheduler.remediation_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1, "countdown": 3600}, # Hourly retry for sweep
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_remediation_sweep() -> None:
    run_async(_remediation_sweep_logic)


async def _load_active_remediation_connections(db: AsyncSession) -> list[Any]:
    connections = await list_active_connections_all_tenants(
        db,
        with_for_update=True,
        skip_locked=True,
    )
    return [conn for conn in connections if is_connection_active(conn)]


async def _remediation_sweep_logic() -> None:
    job_name = "weekly_remediation_sweep"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (
                    asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                ) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
                    connections = await _load_active_remediation_connections(db)

                    now = datetime.now(timezone.utc)
                    bucket_str = now.strftime("%Y-W%U")
                    jobs_to_insert = []
                    orchestrator = SchedulerOrchestrator(async_session_maker)

                    for conn in connections:
                        resolved_provider = resolve_provider_from_connection(conn)
                        provider = normalize_provider(resolved_provider)
                        if not provider:
                            logger.warning(
                                "remediation_sweep_skipping_unknown_provider",
                                provider=resolved_provider or None,
                                connection_id=str(getattr(conn, "id", "unknown")),
                                tenant_id=str(getattr(conn, "tenant_id", "unknown")),
                            )
                            continue
                        connection_id = getattr(conn, "id", None)
                        tenant_id = getattr(conn, "tenant_id", None)
                        if not isinstance(connection_id, UUID) or not isinstance(tenant_id, UUID):
                            logger.warning(
                                "remediation_sweep_skipping_invalid_connection_identity",
                                provider=provider,
                                connection_id=str(connection_id),
                                tenant_id=str(tenant_id),
                            )
                            continue
                        connection_region = resolve_connection_region(conn)

                        # Unified green window logic (H-2: Deduplicated scheduling logic)
                        # Carbon cache is now leveraged correctly within this task run.
                        # Apply carbon-aware delay whenever a concrete region is known.
                        is_green = True
                        if connection_region != "global":
                            is_green = await orchestrator.is_low_carbon_window(
                                connection_region
                            )

                        scheduled_time = now
                        if not is_green:
                            scheduled_time += timedelta(hours=4)

                        dedup_key = (
                            f"{tenant_id}:{provider}:{connection_id}:"
                            f"{JobType.REMEDIATION.value}:{bucket_str}"
                        )
                        jobs_to_insert.append({
                            "job_type": JobType.REMEDIATION.value,
                            "tenant_id": tenant_id,
                            "payload": {
                                "provider": provider,
                                "connection_id": str(connection_id),
                                "region": connection_region,
                            },
                            "status": JobStatus.PENDING,
                            "scheduled_for": scheduled_time,
                            "created_at": now,
                            "deduplication_key": dedup_key,
                        })

                    # Atomic Bulk Insert
                    jobs_enqueued = 0
                    if jobs_to_insert:
                        for i in range(0, len(jobs_to_insert), 500):
                            chunk = jobs_to_insert[i:i+500]
                            stmt = (
                                insert(BackgroundJob)
                                .values(chunk)
                                .on_conflict_do_nothing(
                                    index_elements=["deduplication_key"]
                                )
                            )
                            result_proxy = await db.execute(stmt)
                            if hasattr(result_proxy, "rowcount"):
                                jobs_enqueued += result_proxy.rowcount

                    logger.info(
                        "auto_remediation_sweep_completed",
                        count=len(connections),
                        jobs_enqueued=jobs_enqueued,
                    )

            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            break
        except Exception as e:
            retry_count += 1
            logger.error(
                "auto_remediation_sweep_failed", error=str(e), attempt=retry_count
            )
            if retry_count == max_retries:
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            else:
                await asyncio.sleep(2 ** (retry_count - 1))

    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)


@shared_task(
    name="scheduler.billing_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 600},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_billing_sweep() -> None:
    run_async(_billing_sweep_logic)


async def _billing_sweep_logic() -> None:
    from app.modules.billing.domain.billing.paystack_billing import (
        TenantSubscription,
        SubscriptionStatus,
    )

    job_name = "daily_billing_sweep"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (
                    asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                ) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
                    query = (
                        sa.select(TenantSubscription)
                        .where(
                            TenantSubscription.status == SubscriptionStatus.ACTIVE.value,
                            TenantSubscription.next_payment_date
                            <= datetime.now(timezone.utc),
                            TenantSubscription.paystack_auth_code.isnot(None),
                        )
                        .with_for_update(skip_locked=True)
                    )

                    result = await db.execute(query)
                    due_subscriptions = result.scalars().all()

                    now = datetime.now(timezone.utc)
                    bucket_str = now.strftime("%Y-%m-%d")
                    jobs_enqueued = 0

                    for sub in due_subscriptions:
                        dedup_key = f"{sub.tenant_id}:{JobType.RECURRING_BILLING.value}:{bucket_str}"
                        stmt = (
                            insert(BackgroundJob)
                            .values(
                                job_type=JobType.RECURRING_BILLING.value,
                                tenant_id=sub.tenant_id,
                                payload={"subscription_id": str(sub.id)},
                                status=JobStatus.PENDING,
                                scheduled_for=now,
                                created_at=now,
                                deduplication_key=dedup_key,
                            )
                            .on_conflict_do_nothing(index_elements=["deduplication_key"])
                        )

                        result_proxy = await db.execute(stmt)
                        if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
                            jobs_enqueued += 1
                            BACKGROUND_JOBS_ENQUEUED.labels(
                                job_type=JobType.RECURRING_BILLING.value, cohort="BILLING"
                            ).inc()

                    logger.info(
                        "billing_sweep_completed",
                        due_count=len(due_subscriptions),
                        jobs_enqueued=jobs_enqueued,
                    )
            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            break
        except Exception as e:
            retry_count += 1
            logger.error("billing_sweep_failed", error=str(e), attempt=retry_count)
            if retry_count == max_retries:
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            else:
                await asyncio.sleep(2 ** (retry_count - 1))

    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)


@shared_task(
    name="scheduler.acceptance_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 1800},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_acceptance_sweep() -> None:
    """
    Enqueue daily acceptance-suite evidence capture jobs (per tenant).

    This is designed to be non-invasive (no Slack/Jira spam) while still
    producing audit-grade evidence snapshots for production sign-off.
    """
    run_async(_acceptance_sweep_logic)


async def _acceptance_sweep_logic() -> None:
    job_name = "daily_acceptance_sweep"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with _open_db_session() as db:
                begin_ctx = db.begin()
                if (
                    asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                ) and not hasattr(begin_ctx, "__aenter__"):
                    begin_ctx = await begin_ctx
                async with begin_ctx:
                    result = await db.execute(
                        sa.select(Tenant).with_for_update(skip_locked=True)
                    )
                    tenants = result.scalars().all()
                    if not tenants:
                        logger.info("acceptance_sweep_no_tenants")
                        return

                    now = datetime.now(timezone.utc)
                    bucket_str = now.strftime("%Y-%m-%d")
                    jobs_enqueued = 0
                    capture_close_package = (
                        now.day == 1
                    )  # month-end close evidence capture
                    capture_quarterly_report = now.day == 1 and now.month in {
                        1,
                        4,
                        7,
                        10,
                    }

                    for tenant in tenants:
                        dedup_key = f"{tenant.id}:{JobType.ACCEPTANCE_SUITE_CAPTURE.value}:{bucket_str}"
                        payload: dict[str, Any] | None = None
                        if capture_close_package or capture_quarterly_report:
                            payload = {}
                            if capture_close_package:
                                payload["capture_close_package"] = True
                            if capture_quarterly_report:
                                payload["capture_quarterly_report"] = True
                        stmt = (
                            insert(BackgroundJob)
                            .values(
                                job_type=JobType.ACCEPTANCE_SUITE_CAPTURE.value,
                                tenant_id=tenant.id,
                                status=JobStatus.PENDING,
                                scheduled_for=now,
                                created_at=now,
                                payload=payload,
                                deduplication_key=dedup_key,
                                priority=0,
                            )
                            .on_conflict_do_nothing(
                                index_elements=["deduplication_key"]
                            )
                        )

                        result_proxy = await db.execute(stmt)
                        if (
                            hasattr(result_proxy, "rowcount")
                            and result_proxy.rowcount > 0
                        ):
                            jobs_enqueued += 1
                            BACKGROUND_JOBS_ENQUEUED.labels(
                                job_type=JobType.ACCEPTANCE_SUITE_CAPTURE.value,
                                cohort="ACCEPTANCE",
                            ).inc()

                    logger.info(
                        "acceptance_sweep_enqueued",
                        tenants=len(tenants),
                        jobs_enqueued=jobs_enqueued,
                        bucket=bucket_str,
                    )

            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            break
        except Exception as e:  # noqa: BLE001
            retry_count += 1
            logger.error("acceptance_sweep_failed", error=str(e), attempt=retry_count)
            if retry_count == max_retries:
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            else:
                await asyncio.sleep(2 ** (retry_count - 1))

    duration = time.time() - start_time
    SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)


@shared_task(
    name="scheduler.maintenance_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1, "countdown": 7200}, # 2h retry for maintenance
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_maintenance_sweep() -> None:
    run_async(_maintenance_sweep_logic)


async def _maintenance_sweep_logic() -> None:
    async with _open_db_session() as db:
        # 0. Finalize cost records
        try:
            persistence = CostPersistenceService(db)
            result = await persistence.finalize_batch(days_ago=2)
            logger.info(
                "maintenance_cost_finalization_success",
                records=result.get("records_finalized", 0),
            )
        except Exception as e:
            logger.warning("maintenance_cost_finalization_failed", error=str(e))

        # 0a. Auto-activate the latest staged carbon factor set (guardrailed).
        # This keeps carbon assurance methodology current without manual API calls.
        try:
            from app.modules.reporting.domain.carbon_factors import CarbonFactorService

            factor_refresh_result = await CarbonFactorService(db).auto_activate_latest()
            commit_result = db.commit()
            if inspect.isawaitable(commit_result):
                await commit_result
            logger.info(
                "maintenance_carbon_factor_refresh_success",
                status=factor_refresh_result.get("status"),
                active_factor_set_id=factor_refresh_result.get("active_factor_set_id"),
                candidate_factor_set_id=factor_refresh_result.get(
                    "candidate_factor_set_id"
                ),
            )
        except Exception as e:  # noqa: BLE001
            rollback_result = db.rollback()
            if inspect.isawaitable(rollback_result):
                await rollback_result
            logger.warning("maintenance_carbon_factor_refresh_failed", error=str(e))

        # 0b. Compute realized savings evidence (best-effort, bounded).
        # This keeps Savings Proof procurement outputs finance-grade without requiring a manual operator run.
        try:
            from app.models.realized_savings import RealizedSavingsEvent
            from app.models.remediation import RemediationRequest, RemediationStatus
            from app.modules.reporting.domain.realized_savings import (
                RealizedSavingsService,
            )

            now = datetime.now(timezone.utc)
            executed_before = now - timedelta(
                days=8
            )  # default 7d baseline + 1d gap + 7d measurement (as-of yesterday)
            executed_after = now - timedelta(days=90)
            recompute_cutoff = now - timedelta(hours=24)
            providers = ["saas", "license", "platform", "hybrid"]

            stmt = (
                sa.select(RemediationRequest)
                .outerjoin(
                    RealizedSavingsEvent,
                    sa.and_(
                        RealizedSavingsEvent.tenant_id == RemediationRequest.tenant_id,
                        RealizedSavingsEvent.remediation_request_id
                        == RemediationRequest.id,
                    ),
                )
                .where(
                    RemediationRequest.status == RemediationStatus.COMPLETED.value,
                    RemediationRequest.executed_at.is_not(None),
                    RemediationRequest.executed_at <= executed_before,
                    RemediationRequest.executed_at >= executed_after,
                    RemediationRequest.connection_id.is_not(None),
                    RemediationRequest.provider.in_(providers),
                    sa.or_(
                        RealizedSavingsEvent.id.is_(None),
                        RealizedSavingsEvent.computed_at < recompute_cutoff,
                    ),
                )
                .order_by(RemediationRequest.executed_at.desc())
                .limit(200)
            )
            remediation_requests = list((await db.execute(stmt)).scalars().all())
            if remediation_requests:
                service = RealizedSavingsService(db)
                computed = 0
                for req in remediation_requests:
                    event = await service.compute_for_request(
                        tenant_id=req.tenant_id,
                        request=req,
                        require_final=True,
                    )
                    if event is not None:
                        computed += 1
                await db.commit()
                logger.info(
                    "maintenance_realized_savings_compute_success",
                    scanned=len(remediation_requests),
                    computed=computed,
                )
            else:
                logger.info(
                    "maintenance_realized_savings_compute_skipped",
                    reason="no_eligible_remediations",
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("maintenance_realized_savings_compute_failed", error=str(e))

        # 1. Refresh View
        aggregator = CostAggregator()
        await aggregator.refresh_materialized_view(db)

        # 2. Partition Maintenance (Automated Rollover)
        try:
            from app.shared.core.maintenance import PartitionMaintenanceService
            maintenance = PartitionMaintenanceService(db)
            
            # Pre-create partitions for the next 3 months to ensure zero downtime
            partitions_created = await maintenance.create_future_partitions(months_ahead=3)
            
            # Archive old data (older than 13 months)
            archived_count = await maintenance.archive_old_partitions(months_old=13)
            
            await db.commit()
            logger.info(
                "maintenance_partitioning_success", 
                created=partitions_created,
                archived=archived_count
            )
        except Exception as e:
            await db.rollback()
            logger.error("maintenance_partitioning_failed", error=str(e))


@shared_task(
    name="scheduler.currency_sync",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 5, "countdown": 300},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_currency_sync() -> None:
    """
    Celery task to refresh currency exchange rates.
    """
    # Fetch common currencies to trigger refresh and Redis sync
    for curr in ["NGN", "EUR", "GBP"]:
        run_async(get_exchange_rate, curr)
    logger.info("currency_sync_completed")


@shared_task(name="scheduler.daily_scan")  # type: ignore[untyped-decorator]
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
                "daily_finops_scan_partial_failure", cohort=cohort.value, error=str(e)
            )

    duration = time.time() - start_time
    logger.info(
        "daily_finops_scan_completed",
        duration_seconds=duration,
        successful=successful_dispatches,
        failed=failed_dispatches,
    )
