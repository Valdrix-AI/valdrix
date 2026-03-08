from __future__ import annotations

from typing import Any, Callable


def normalize_cost_retention_summary(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"deleted_count": 0, "tiers": {}, "tenant_reports": []}

    try:
        deleted_count = int(raw.get("deleted_count", 0) or 0)
    except (TypeError, ValueError):
        deleted_count = 0

    tiers = raw.get("tiers", {})
    tenant_reports = raw.get("tenant_reports", [])
    return {
        "deleted_count": deleted_count if deleted_count >= 0 else 0,
        "tiers": tiers if isinstance(tiers, dict) else {},
        "tenant_reports": tenant_reports if isinstance(tenant_reports, list) else [],
        "batch_size": raw.get("batch_size"),
        "max_batches": raw.get("max_batches"),
        "as_of_date": raw.get("as_of_date"),
    }


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
    recoverable_errors: tuple[type[Exception], ...],
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
            except recoverable_errors as exc:
                logger.warning("maintenance_cost_finalization_failed", error=str(exc))

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
            except recoverable_errors as exc:
                rollback_result = db.rollback()
                if inspect_module.isawaitable(rollback_result):
                    await rollback_result
                logger.warning("maintenance_carbon_factor_refresh_failed", error=str(exc))

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
            except recoverable_errors as exc:
                logger.warning("maintenance_realized_savings_compute_failed", error=str(exc))

            try:
                from app.shared.core.cloud_pricing_data import (
                    refresh_cloud_resource_pricing,
                )

                refreshed = await refresh_cloud_resource_pricing(db)
                logger.info(
                    "maintenance_cloud_pricing_refresh_success",
                    refreshed_records=refreshed,
                )
            except recoverable_errors as exc:
                logger.warning("maintenance_cloud_pricing_refresh_failed", error=str(exc))

            try:
                from uuid import uuid4

                from app.modules.governance.domain.security.audit_log import (
                    AuditEventType,
                    AuditLogger,
                )
                from app.shared.core.config import get_settings
                from app.shared.core.ops_metrics import record_cost_retention_purge

                settings = get_settings()
                cleanup_fn = getattr(persistence, "cleanup_expired_records_by_plan", None)
                raw_retention_summary: Any = None
                if callable(cleanup_fn):
                    raw_retention_summary = cleanup_fn(
                        batch_size=getattr(
                            settings,
                            "COST_RECORD_RETENTION_PURGE_BATCH_SIZE",
                            5000,
                        ),
                        max_batches=getattr(
                            settings,
                            "COST_RECORD_RETENTION_PURGE_MAX_BATCHES",
                            50,
                        ),
                    )
                    if inspect_module.isawaitable(raw_retention_summary):
                        raw_retention_summary = await raw_retention_summary

                retention_summary = normalize_cost_retention_summary(
                    raw_retention_summary
                )
                if retention_summary["deleted_count"] > 0:
                    retention_run_id = str(uuid4())
                    for tenant_report in retention_summary["tenant_reports"]:
                        tenant_id = tenant_report.get("tenant_id")
                        if not tenant_id:
                            continue
                        audit = AuditLogger(
                            db=db,
                            tenant_id=tenant_id,
                            correlation_id=retention_run_id,
                        )
                        await audit.log(
                            event_type=AuditEventType.SYSTEM_MAINTENANCE,
                            actor_id=None,
                            actor_email=None,
                            resource_type="cost_records_retention",
                            resource_id=str(
                                tenant_report.get("tenant_tier") or "unknown"
                            ),
                            details={
                                "run_id": retention_run_id,
                                "captured_at": datetime_cls.now(
                                    timezone_obj.utc
                                ).isoformat(),
                                "retention": tenant_report,
                                "summary": {
                                    "deleted_count": retention_summary["deleted_count"],
                                    "tiers": retention_summary["tiers"],
                                    "batch_size": retention_summary["batch_size"],
                                    "max_batches": retention_summary["max_batches"],
                                    "as_of_date": retention_summary["as_of_date"],
                                },
                            },
                            success=True,
                            request_method="SCHEDULER",
                            request_path="/scheduler/maintenance_sweep/cost_records_retention",
                        )

                    retention_commit_result = db.commit()
                    if inspect_module.isawaitable(retention_commit_result):
                        await retention_commit_result

                for tier_name, deleted_count in retention_summary["tiers"].items():
                    record_cost_retention_purge(
                        str(tier_name),
                        int(deleted_count or 0),
                    )
                logger.info("maintenance_cost_retention_success", **retention_summary)
            except recoverable_errors as exc:
                retention_rollback_result = db.rollback()
                if inspect_module.isawaitable(retention_rollback_result):
                    await retention_rollback_result
                logger.warning("maintenance_cost_retention_failed", error=str(exc))

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
            except recoverable_errors as exc:
                await db.rollback()
                logger.error("maintenance_partitioning_failed", error=str(exc))

            try:
                from app.models.background_job import BackgroundJob, JobStatus
                from app.shared.core.config import get_settings
                from app.tasks.scheduler_background_job_retention_ops import (
                    purge_terminal_background_jobs,
                )

                purge_summary = await purge_terminal_background_jobs(
                    db=db,
                    sa=sa,
                    logger=logger,
                    background_job_model=BackgroundJob,
                    job_status=JobStatus,
                    datetime_cls=datetime_cls,
                    timezone_obj=timezone_obj,
                    timedelta_cls=timedelta_cls,
                    get_settings_fn=get_settings,
                )
                if purge_summary["total_deleted"] > 0:
                    retention_commit_result = db.commit()
                    if inspect_module.isawaitable(retention_commit_result):
                        await retention_commit_result
                logger.info("maintenance_background_jobs_retention_success", **purge_summary)
            except recoverable_errors as exc:
                retention_rollback_result = db.rollback()
                if inspect_module.isawaitable(retention_rollback_result):
                    await retention_rollback_result
                logger.warning("maintenance_background_jobs_retention_failed", error=str(exc))

