from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.exc import SQLAlchemyError

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
    start_time = time_module.time()
    max_retries = 3
    retry_count = 0

    with scheduler_span_fn("scheduler.billing_sweep", job_name=job_name):
        while retry_count < max_retries:
            try:
                async with open_db_session_fn() as db:
                    begin_ctx = db.begin()
                    if (
                        asyncio_module.iscoroutine(begin_ctx)
                        or inspect.isawaitable(begin_ctx)
                    ) and not hasattr(begin_ctx, "__aenter__"):
                        begin_ctx = await begin_ctx
                    async with begin_ctx:
                        query = (
                            sa.select(TenantSubscription)
                            .where(
                                TenantSubscription.status
                                == SubscriptionStatus.ACTIVE.value,
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
                                background_jobs_enqueued.labels(
                                    job_type=job_type.RECURRING_BILLING.value,
                                    cohort="BILLING",
                                ).inc()

                        logger.info(
                            "billing_sweep_completed",
                            due_count=len(due_subscriptions),
                            jobs_enqueued=jobs_enqueued,
                        )
                scheduler_job_runs.labels(job_name=job_name, status="success").inc()
                break
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                retry_count += 1
                logger.error("billing_sweep_failed", error=str(e), attempt=retry_count)
                if retry_count == max_retries:
                    scheduler_job_runs.labels(
                        job_name=job_name, status="failure"
                    ).inc()
                else:
                    await asyncio_module.sleep(2 ** (retry_count - 1))

        duration = time_module.time() - start_time
        scheduler_job_duration.labels(job_name=job_name).observe(duration)


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
    start_time = __import__("time").time()
    max_retries = 3
    retry_count = 0

    with scheduler_span_fn("scheduler.acceptance_sweep", job_name=job_name):
        while retry_count < max_retries:
            try:
                async with open_db_session_fn() as db:
                    begin_ctx = db.begin()
                    if (
                        asyncio_module.iscoroutine(begin_ctx)
                        or inspect.isawaitable(begin_ctx)
                    ) and not hasattr(begin_ctx, "__aenter__"):
                        begin_ctx = await begin_ctx
                    async with begin_ctx:
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
                                background_jobs_enqueued.labels(
                                    job_type=job_type.ACCEPTANCE_SUITE_CAPTURE.value,
                                    cohort="ACCEPTANCE",
                                ).inc()

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

        duration = __import__("time").time() - start_time
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
    with scheduler_span_fn("scheduler.maintenance_sweep", job_name="maintenance_sweep"):
        async with open_db_session_fn() as db:
            try:
                persistence = cost_persistence_service_cls(db)
                result = await persistence.finalize_batch(days_ago=2)
                logger.info(
                    "maintenance_cost_finalization_success",
                    records=result.get("records_finalized", 0),
                )
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                logger.warning("maintenance_cost_finalization_failed", error=str(e))

            try:
                from app.modules.reporting.domain.carbon_factors import CarbonFactorService

                factor_refresh_result = await CarbonFactorService(db).auto_activate_latest()
                commit_result = db.commit()
                if inspect_module.isawaitable(commit_result):
                    await commit_result
                logger.info(
                    "maintenance_carbon_factor_refresh_success",
                    status=factor_refresh_result.get("status"),
                    active_factor_set_id=factor_refresh_result.get("active_factor_set_id"),
                    candidate_factor_set_id=factor_refresh_result.get(
                        "candidate_factor_set_id"
                    ),
                )
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                rollback_result = db.rollback()
                if inspect_module.isawaitable(rollback_result):
                    await rollback_result
                logger.warning("maintenance_carbon_factor_refresh_failed", error=str(e))

            try:
                from app.models.realized_savings import RealizedSavingsEvent
                from app.models.remediation import RemediationRequest, RemediationStatus
                from app.modules.reporting.domain.realized_savings import (
                    RealizedSavingsService,
                )

                now = datetime_cls.now(timezone_obj.utc)
                executed_before = now - timedelta_cls(days=8)
                executed_after = now - timedelta_cls(days=90)
                recompute_cutoff = now - timedelta_cls(hours=24)
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
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                logger.warning("maintenance_realized_savings_compute_failed", error=str(e))

            aggregator = cost_aggregator_cls()
            await aggregator.refresh_materialized_view(db)

            try:
                from app.shared.core.maintenance import PartitionMaintenanceService

                maintenance = PartitionMaintenanceService(db)
                partitions_created = await maintenance.create_future_partitions(
                    months_ahead=3
                )
                archived_count = await maintenance.archive_old_partitions(months_old=13)

                await db.commit()
                logger.info(
                    "maintenance_partitioning_success",
                    created=partitions_created,
                    archived=archived_count,
                )
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                await db.rollback()
                logger.error("maintenance_partitioning_failed", error=str(e))


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
    start_time = time_module.time()
    max_retries = 3
    retry_count = 0

    with scheduler_span_fn(
        "scheduler.enforcement_reconciliation_sweep", job_name=job_name
    ):
        while retry_count < max_retries:
            try:
                async with open_db_session_fn() as db:
                    begin_ctx = db.begin()
                    if (
                        asyncio_module.iscoroutine(begin_ctx)
                        or inspect.isawaitable(begin_ctx)
                    ) and not hasattr(begin_ctx, "__aenter__"):
                        begin_ctx = await begin_ctx
                    async with begin_ctx:
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
                            if (
                                hasattr(result_proxy, "rowcount")
                                and result_proxy.rowcount > 0
                            ):
                                jobs_enqueued += 1
                                background_jobs_enqueued.labels(
                                    job_type=job_type.ENFORCEMENT_RECONCILIATION.value,
                                    cohort="ENFORCEMENT",
                                ).inc()

                        logger.info(
                            "enforcement_reconciliation_sweep_enqueued",
                            tenants=len(tenant_ids),
                            jobs_enqueued=jobs_enqueued,
                            bucket=bucket_str,
                        )

                scheduler_job_runs.labels(job_name=job_name, status="success").inc()
                break
            except SCHEDULER_SWEEP_RECOVERABLE_ERRORS as e:
                retry_count += 1
                logger.error(
                    "enforcement_reconciliation_sweep_failed",
                    error=str(e),
                    attempt=retry_count,
                )
                if retry_count == max_retries:
                    scheduler_job_runs.labels(
                        job_name=job_name, status="failure"
                    ).inc()
                else:
                    await asyncio_module.sleep(2 ** (retry_count - 1))

        duration = time_module.time() - start_time
        scheduler_job_duration.labels(job_name=job_name).observe(duration)
