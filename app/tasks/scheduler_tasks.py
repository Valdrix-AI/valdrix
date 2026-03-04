import asyncio
from typing import Any, AsyncGenerator, ContextManager, Coroutine, Sequence, cast
import structlog
from celery import shared_task
from app.shared.db.session import async_session_maker, mark_session_system_context
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
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
from app.shared.core.config import get_settings
from app.shared.core.tracing import get_tracer
from app.tasks.scheduler_sweep_ops import (
    acceptance_sweep_logic as _acceptance_sweep_logic_impl,
    billing_sweep_logic as _billing_sweep_logic_impl,
    enforcement_reconciliation_sweep_logic as _enforcement_reconciliation_sweep_logic_impl,
    maintenance_sweep_logic as _maintenance_sweep_logic_impl,
)
from app.tasks.scheduler_runtime_ops import (
    cap_scope_items as _cap_scope_items_impl,
    coerce_positive_limit as _coerce_positive_limit_impl,
    open_db_session as _open_db_session_impl,
    scheduler_span as _scheduler_span_impl,
    system_sweep_connection_limit as _system_sweep_connection_limit_impl,
    system_sweep_tenant_limit as _system_sweep_tenant_limit_impl,
)

logger = structlog.get_logger()
tracer = get_tracer(__name__)
SCHEDULER_RECOVERABLE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    AttributeError,
    asyncio.TimeoutError,
    SQLAlchemyError,
)
_coerce_positive_limit = _coerce_positive_limit_impl

def _system_sweep_tenant_limit() -> int:
    return _system_sweep_tenant_limit_impl(
        get_settings_fn=get_settings,
        coerce_positive_limit_fn=_coerce_positive_limit,
    )

def _system_sweep_connection_limit() -> int:
    return _system_sweep_connection_limit_impl(
        get_settings_fn=get_settings,
        coerce_positive_limit_fn=_coerce_positive_limit,
    )

def _cap_scope_items(items: Sequence[Any], *, scope: str, limit: int) -> list[Any]:
    return _cap_scope_items_impl(
        items,
        scope=scope,
        limit=limit,
        logger=logger,
    )

def _scheduler_span(name: str, **attributes: object) -> ContextManager[None]:
    return _scheduler_span_impl(
        name,
        tracer=tracer,
        **attributes,
    )

@asynccontextmanager
async def _open_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _open_db_session_impl(
        async_session_maker_fn=async_session_maker,
        mark_session_system_context_fn=mark_session_system_context,
        logger=logger,
        asyncio_module=asyncio,
    ) as session:
        yield session

# Helper to run async code in sync Celery task
def run_async(task_or_coro: Any, *args: Any, **kwargs: Any) -> Any:
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
    if isinstance(cohort_value, TenantCohort):
        cohort = cohort_value
    else:
        try:
            cohort = TenantCohort[cohort_value]
        except KeyError:
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

    with _scheduler_span(
        "scheduler.cohort_analysis",
        job_name=job_name,
        cohort=target_cohort.value,
        correlation_id=job_id,
    ):
        while retry_count < max_retries:
            try:
                async with _open_db_session() as db:
                    begin_ctx = db.begin()
                    if (
                        asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                    ) and not hasattr(begin_ctx, "__aenter__"):
                        begin_ctx = await begin_ctx
                    async with begin_ctx:
                        with _scheduler_span(
                            "scheduler.cohort_analysis.load_tenants",
                            cohort=target_cohort.value,
                            retry_count=retry_count,
                        ):
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
                            tenant_limit = _system_sweep_tenant_limit()
                            cohort_tenants = _cap_scope_items(
                                cohort_tenants,
                                scope=f"cohort:{target_cohort.value}",
                                limit=tenant_limit,
                            )

                        if not cohort_tenants:
                            logger.info(
                                "scheduler_cohort_empty", cohort=target_cohort.value
                            )
                            return

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

                        with _scheduler_span(
                            "scheduler.cohort_analysis.build_jobs",
                            cohort=target_cohort.value,
                            tenant_count=len(cohort_tenants),
                        ):
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

                        jobs_enqueued = 0
                        if jobs_to_insert:
                            with _scheduler_span(
                                "scheduler.cohort_analysis.insert_jobs",
                                cohort=target_cohort.value,
                                job_count=len(jobs_to_insert),
                            ):
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
                                        count = result_proxy.rowcount
                                        jobs_enqueued += count

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
                break

            except SCHEDULER_RECOVERABLE_ERRORS as e:
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

    with _scheduler_span("scheduler.remediation_sweep", job_name=job_name):
        while retry_count < max_retries:
            try:
                async with _open_db_session() as db:
                    begin_ctx = db.begin()
                    if (
                        asyncio.iscoroutine(begin_ctx) or inspect.isawaitable(begin_ctx)
                    ) and not hasattr(begin_ctx, "__aenter__"):
                        begin_ctx = await begin_ctx
                    async with begin_ctx:
                        with _scheduler_span(
                            "scheduler.remediation_sweep.load_connections",
                            retry_count=retry_count,
                        ):
                            connections = await _load_active_remediation_connections(db)
                            connection_limit = _system_sweep_connection_limit()
                            connections = _cap_scope_items(
                                connections,
                                scope="remediation_connections",
                                limit=connection_limit,
                            )

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

                        jobs_enqueued = 0
                        if jobs_to_insert:
                            with _scheduler_span(
                                "scheduler.remediation_sweep.insert_jobs",
                                connection_count=len(connections),
                                job_count=len(jobs_to_insert),
                            ):
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
            except SCHEDULER_RECOVERABLE_ERRORS as e:
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
    await _billing_sweep_logic_impl(
        open_db_session_fn=_open_db_session,
        scheduler_span_fn=_scheduler_span,
        logger=logger,
        scheduler_job_runs=SCHEDULER_JOB_RUNS,
        scheduler_job_duration=SCHEDULER_JOB_DURATION,
        background_jobs_enqueued=BACKGROUND_JOBS_ENQUEUED,
        sa=sa,
        insert=insert,
        background_job_model=BackgroundJob,
        job_status=JobStatus,
        job_type=JobType,
        time_module=time,
        asyncio_module=asyncio,
    )


@shared_task(
    name="scheduler.acceptance_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 1800},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_acceptance_sweep() -> None:
    run_async(_acceptance_sweep_logic)


async def _acceptance_sweep_logic() -> None:
    await _acceptance_sweep_logic_impl(
        open_db_session_fn=_open_db_session,
        scheduler_span_fn=_scheduler_span,
        logger=logger,
        scheduler_job_runs=SCHEDULER_JOB_RUNS,
        scheduler_job_duration=SCHEDULER_JOB_DURATION,
        background_jobs_enqueued=BACKGROUND_JOBS_ENQUEUED,
        sa=sa,
        insert=insert,
        tenant_model=Tenant,
        background_job_model=BackgroundJob,
        job_status=JobStatus,
        job_type=JobType,
        system_sweep_tenant_limit_fn=_system_sweep_tenant_limit,
        cap_scope_items_fn=_cap_scope_items,
        datetime_module=datetime,
        timezone_obj=timezone,
        asyncio_module=asyncio,
    )


@shared_task(
    name="scheduler.maintenance_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1, "countdown": 7200}, # 2h retry for maintenance
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_maintenance_sweep() -> None:
    run_async(_maintenance_sweep_logic)


async def _maintenance_sweep_logic() -> None:
    await _maintenance_sweep_logic_impl(
        open_db_session_fn=_open_db_session,
        scheduler_span_fn=_scheduler_span,
        logger=logger,
        cost_persistence_service_cls=CostPersistenceService,
        cost_aggregator_cls=CostAggregator,
        sa=sa,
        inspect_module=inspect,
        datetime_cls=datetime,
        timezone_obj=timezone,
        timedelta_cls=timedelta,
    )


@shared_task(
    name="scheduler.currency_sync",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 5, "countdown": 300},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_currency_sync() -> None:
    for curr in ["NGN", "EUR", "GBP"]:
        run_async(get_exchange_rate, curr)
    logger.info("currency_sync_completed")


@shared_task(
    name="scheduler.enforcement_reconciliation_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 900},
    retry_backoff=True,
)  # type: ignore[untyped-decorator]
def run_enforcement_reconciliation_sweep() -> None:
    run_async(_enforcement_reconciliation_sweep_logic)


async def _enforcement_reconciliation_sweep_logic() -> None:
    await _enforcement_reconciliation_sweep_logic_impl(
        get_settings_fn=get_settings,
        open_db_session_fn=_open_db_session,
        scheduler_span_fn=_scheduler_span,
        logger=logger,
        scheduler_job_runs=SCHEDULER_JOB_RUNS,
        scheduler_job_duration=SCHEDULER_JOB_DURATION,
        background_jobs_enqueued=BACKGROUND_JOBS_ENQUEUED,
        sa=sa,
        insert=insert,
        tenant_model=Tenant,
        background_job_model=BackgroundJob,
        job_status=JobStatus,
        job_type=JobType,
        system_sweep_tenant_limit_fn=_system_sweep_tenant_limit,
        cap_scope_items_fn=_cap_scope_items,
        datetime_cls=datetime,
        timezone_obj=timezone,
        time_module=time,
        asyncio_module=asyncio,
    )


@shared_task(name="scheduler.daily_scan")  # type: ignore[untyped-decorator]
def daily_finops_scan() -> None:
    logger.info("daily_finops_scan_started")
    start_time = time.time()
    successful_dispatches = 0
    failed_dispatches = 0

    for cohort in TenantCohort:
        try:
            run_cohort_analysis.delay(cohort.value)
            successful_dispatches += 1
            logger.info("cohort_analysis_dispatched", cohort=cohort.value)
        except SCHEDULER_RECOVERABLE_ERRORS as e:
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
