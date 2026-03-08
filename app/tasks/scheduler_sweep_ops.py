from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import SQLAlchemyError

from app.tasks.scheduler_sweep_runtime import (
    increment_background_job_metric,
    open_transaction_session,
    run_sweep_with_retries,
)
from app.tasks.scheduler_maintenance_ops import (
    maintenance_sweep_logic as run_maintenance_sweep_logic,
)

SCHEDULER_SWEEP_RECOVERABLE_ERRORS = (
    SQLAlchemyError,
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)

async def billing_sweep_logic(
    *,
    open_db_session_fn: Callable[[], Any],
    scheduler_span_fn: Callable[..., Any],
    logger: Any,
    scheduler_job_runs: Any,
    scheduler_job_duration: Any,
    background_jobs_enqueued: Any,
    sa: Any,
    insert: Any,
    background_job_model: Any,
    job_status: Any,
    job_type: Any,
    time_module: Any,
    asyncio_module: Any,
) -> None:
    from app.modules.billing.domain.billing.paystack_billing import (
        SubscriptionStatus,
        TenantSubscription,
    )

    job_name = "daily_billing_sweep"
    with scheduler_span_fn("scheduler.billing_sweep", job_name=job_name):
        async def _run_once() -> None:
            async with open_transaction_session(
                open_db_session_fn=open_db_session_fn,
                asyncio_module=asyncio_module,
            ) as db:
                query = (
                    sa.select(TenantSubscription)
                    .where(
                        TenantSubscription.status == SubscriptionStatus.ACTIVE.value,
                        TenantSubscription.next_payment_date <= datetime.now(timezone.utc),
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
                    dedup_key = (
                        f"{sub.tenant_id}:{job_type.RECURRING_BILLING.value}:{bucket_str}"
                    )
                    stmt = (
                        insert(background_job_model)
                        .values(
                            job_type=job_type.RECURRING_BILLING.value,
                            tenant_id=sub.tenant_id,
                            payload={"subscription_id": str(sub.id)},
                            status=job_status.PENDING,
                            scheduled_for=now,
                            created_at=now,
                            deduplication_key=dedup_key,
                        )
                        .on_conflict_do_nothing(index_elements=["deduplication_key"])
                    )
                    result_proxy = await db.execute(stmt)
                    if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
                        jobs_enqueued += 1
                        increment_background_job_metric(
                            background_jobs_enqueued=background_jobs_enqueued,
                            job_type_value=job_type.RECURRING_BILLING.value,
                            cohort="BILLING",
                        )

                logger.info(
                    "billing_sweep_completed",
                    due_count=len(due_subscriptions),
                    jobs_enqueued=jobs_enqueued,
                )

        await run_sweep_with_retries(
            job_name=job_name,
            error_event="billing_sweep_failed",
            max_retries=3,
            time_module=time_module,
            asyncio_module=asyncio_module,
            scheduler_job_runs=scheduler_job_runs,
            scheduler_job_duration=scheduler_job_duration,
            logger=logger,
            recoverable_errors=SCHEDULER_SWEEP_RECOVERABLE_ERRORS,
            run_once=_run_once,
        )


async def acceptance_sweep_logic(
    *,
    open_db_session_fn: Callable[[], Any],
    scheduler_span_fn: Callable[..., Any],
    logger: Any,
    scheduler_job_runs: Any,
    scheduler_job_duration: Any,
    background_jobs_enqueued: Any,
    sa: Any,
    insert: Any,
    tenant_model: Any,
    background_job_model: Any,
    job_status: Any,
    job_type: Any,
    system_sweep_tenant_limit_fn: Callable[[], int],
    cap_scope_items_fn: Callable[..., list[Any]],
    datetime_module: Any,
    timezone_obj: Any,
    asyncio_module: Any,
) -> None:
    job_name = "daily_acceptance_sweep"
    start_time = time.time()
    max_retries = 3
    retry_count = 0

    with scheduler_span_fn("scheduler.acceptance_sweep", job_name=job_name):
        while retry_count < max_retries:
            try:
                async with open_transaction_session(
                    open_db_session_fn=open_db_session_fn,
                    asyncio_module=asyncio_module,
                ) as db:
                        result = await db.execute(
                            sa.select(tenant_model).with_for_update(skip_locked=True)
                        )
                        tenant_limit = system_sweep_tenant_limit_fn()
                        tenants = cap_scope_items_fn(
                            result.scalars().all(),
                            scope="acceptance_tenants",
                            limit=tenant_limit,
                        )
                        if not tenants:
                            logger.info("acceptance_sweep_no_tenants")
                            return

                        now = datetime_module.now(timezone_obj.utc)
                        bucket_str = now.strftime("%Y-%m-%d")
                        jobs_enqueued = 0
                        capture_close_package = now.day == 1
                        capture_quarterly_report = now.day == 1 and now.month in {
                            1,
                            4,
                            7,
                            10,
                        }

                        for tenant in tenants:
                            dedup_key = (
                                f"{tenant.id}:{job_type.ACCEPTANCE_SUITE_CAPTURE.value}:{bucket_str}"
                            )
                            payload: dict[str, Any] | None = None
                            if capture_close_package or capture_quarterly_report:
                                payload = {}
                                if capture_close_package:
                                    payload["capture_close_package"] = True
                                if capture_quarterly_report:
                                    payload["capture_quarterly_report"] = True
                            stmt = (
                                insert(background_job_model)
                                .values(
                                    job_type=job_type.ACCEPTANCE_SUITE_CAPTURE.value,
                                    tenant_id=tenant.id,
                                    status=job_status.PENDING,
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
                                increment_background_job_metric(
                                    background_jobs_enqueued=background_jobs_enqueued,
                                    job_type_value=job_type.ACCEPTANCE_SUITE_CAPTURE.value,
                                    cohort="ACCEPTANCE",
                                )

                        logger.info(
                            "acceptance_sweep_enqueued",
                            tenants=len(tenants),
                            jobs_enqueued=jobs_enqueued,
                            bucket=bucket_str,
                        )

                scheduler_job_runs.labels(job_name=job_name, status="success").inc()
                break
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                retry_count += 1
                logger.error(
                    "acceptance_sweep_failed", error=str(e), attempt=retry_count
                )
                if retry_count == max_retries:
                    scheduler_job_runs.labels(
                        job_name=job_name, status="failure"
                    ).inc()
                else:
                    await asyncio_module.sleep(2 ** (retry_count - 1))

        duration = time.time() - start_time
        scheduler_job_duration.labels(job_name=job_name).observe(duration)


async def maintenance_sweep_logic(
    *,
    open_db_session_fn: Callable[[], Any],
    scheduler_span_fn: Callable[..., Any],
    logger: Any,
    cost_persistence_service_cls: Any,
    cost_aggregator_cls: Any,
    sa: Any,
    inspect_module: Any,
    datetime_cls: Any,
    timezone_obj: Any,
    timedelta_cls: Any,
) -> None:
    await run_maintenance_sweep_logic(
        open_db_session_fn=open_db_session_fn,
        scheduler_span_fn=scheduler_span_fn,
        logger=logger,
        cost_persistence_service_cls=cost_persistence_service_cls,
        cost_aggregator_cls=cost_aggregator_cls,
        sa=sa,
        inspect_module=inspect_module,
        datetime_cls=datetime_cls,
        timezone_obj=timezone_obj,
        timedelta_cls=timedelta_cls,
        recoverable_errors=SCHEDULER_SWEEP_RECOVERABLE_ERRORS,
    )


async def enforcement_reconciliation_sweep_logic(
    *,
    get_settings_fn: Callable[[], Any],
    open_db_session_fn: Callable[[], Any],
    scheduler_span_fn: Callable[..., Any],
    logger: Any,
    scheduler_job_runs: Any,
    scheduler_job_duration: Any,
    background_jobs_enqueued: Any,
    sa: Any,
    insert: Any,
    tenant_model: Any,
    background_job_model: Any,
    job_status: Any,
    job_type: Any,
    system_sweep_tenant_limit_fn: Callable[[], int],
    cap_scope_items_fn: Callable[..., list[Any]],
    datetime_cls: Any,
    timezone_obj: Any,
    time_module: Any,
    asyncio_module: Any,
) -> None:
    settings = get_settings_fn()
    if not bool(getattr(settings, "ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED", True)):
        logger.info("enforcement_reconciliation_sweep_disabled")
        return

    job_name = "hourly_enforcement_reconciliation_sweep"
    with scheduler_span_fn(
        "scheduler.enforcement_reconciliation_sweep", job_name=job_name
    ):
        async def _run_once() -> None:
            async with open_transaction_session(
                open_db_session_fn=open_db_session_fn,
                asyncio_module=asyncio_module,
            ) as db:
                result = await db.execute(
                    sa.select(tenant_model.id).with_for_update(skip_locked=True)
                )
                tenant_limit = system_sweep_tenant_limit_fn()
                tenant_ids = cap_scope_items_fn(
                    result.scalars().all(),
                    scope="enforcement_reconciliation_tenants",
                    limit=tenant_limit,
                )
                now = datetime_cls.now(timezone_obj.utc)
                bucket_str = now.replace(
                    minute=0, second=0, microsecond=0
                ).isoformat()
                jobs_enqueued = 0

                for tenant_id in tenant_ids:
                    dedup_key = (
                        f"{tenant_id}:{job_type.ENFORCEMENT_RECONCILIATION.value}:{bucket_str}"
                    )
                    stmt = (
                        insert(background_job_model)
                        .values(
                            job_type=job_type.ENFORCEMENT_RECONCILIATION.value,
                            tenant_id=tenant_id,
                            status=job_status.PENDING,
                            scheduled_for=now,
                            created_at=now,
                            payload={"trigger": "scheduled"},
                            deduplication_key=dedup_key,
                            priority=1,
                        )
                        .on_conflict_do_nothing(index_elements=["deduplication_key"])
                    )
                    result_proxy = await db.execute(stmt)
                    if hasattr(result_proxy, "rowcount") and result_proxy.rowcount > 0:
                        jobs_enqueued += 1
                        increment_background_job_metric(
                            background_jobs_enqueued=background_jobs_enqueued,
                            job_type_value=job_type.ENFORCEMENT_RECONCILIATION.value,
                            cohort="ENFORCEMENT",
                        )

                logger.info(
                    "enforcement_reconciliation_sweep_enqueued",
                    tenants=len(tenant_ids),
                    jobs_enqueued=jobs_enqueued,
                    bucket=bucket_str,
                )

        await run_sweep_with_retries(
            job_name=job_name,
            error_event="enforcement_reconciliation_sweep_failed",
            max_retries=3,
            time_module=time_module,
            asyncio_module=asyncio_module,
            scheduler_job_runs=scheduler_job_runs,
            scheduler_job_duration=scheduler_job_duration,
            logger=logger,
            recoverable_errors=SCHEDULER_SWEEP_RECOVERABLE_ERRORS,
            run_once=_run_once,
        )
