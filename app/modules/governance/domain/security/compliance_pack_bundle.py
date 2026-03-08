from datetime import date, datetime, timezone
from typing import Any, Callable, Optional, cast
from uuid import UUID, uuid4

import csv
import io
import json
import zipfile
import structlog
from sqlalchemy import desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.domain.security.audit_log import (
    AuditEventType,
    AuditLogger,
    AuditLog,
)
from app.modules.governance.domain.security.compliance_pack_evidence import (
    collect_carbon_factor_evidence,
    collect_integration_evidence,
    collect_payload_evidence,
    collect_settings_snapshots,
)
from app.modules.governance.domain.security.compliance_pack_bundle_exports import (
    build_manifest,
    run_close_package_export,
    run_focus_export,
    run_realized_savings_export,
    run_savings_proof_export,
    write_core_artifacts,
)
from app.modules.governance.domain.security.compliance_pack_contracts import (
    CompliancePackActor,
    CompliancePackBundleResult,
    CompliancePackValidationError,
)
from app.modules.governance.domain.security.compliance_pack_bundle_state import (
    build_doc_payloads,
    collect_payload_evidence_map,
    default_included_files,
    initialize_optional_export_state,
    resolve_optional_export_scopes,
)
from app.modules.governance.domain.security.compliance_pack_support import (
    load_reference_documents,
)
from app.shared.core.config import get_settings

logger = structlog.get_logger()

COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    SQLAlchemyError,
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)


async def export_compliance_pack_bundle(
    *,
    actor: CompliancePackActor,
    db: AsyncSession,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    evidence_limit: int,
    include_focus_export: bool,
    focus_provider: Optional[str],
    focus_include_preliminary: bool,
    focus_max_rows: int,
    focus_start_date: Optional[date],
    focus_end_date: Optional[date],
    include_savings_proof: bool,
    savings_provider: Optional[str],
    savings_start_date: Optional[date],
    savings_end_date: Optional[date],
    include_realized_savings: bool,
    realized_provider: Optional[str],
    realized_start_date: Optional[date],
    realized_end_date: Optional[date],
    realized_limit: int,
    include_close_package: bool,
    close_provider: Optional[str],
    close_start_date: Optional[date],
    close_end_date: Optional[date],
    close_enforce_finalized: bool,
    close_max_restatements: int,
    sanitize_csv_cell: Callable[[Any], str],
) -> CompliancePackBundleResult:
    exported_at = datetime.now(timezone.utc)
    run_id = str(uuid4())
    app_settings = get_settings()

    if start_date and end_date and start_date > end_date:
        raise CompliancePackValidationError("start_date must be <= end_date")

    # Record the export request (SOC2 evidence: export access is auditable).
    try:
        audit_logger = AuditLogger(
            db, cast(UUID, actor.tenant_id), correlation_id=run_id
        )
        await audit_logger.log(
            event_type=AuditEventType.EXPORT_REQUESTED,
            actor_id=actor.id,
            actor_email=actor.email,
            request_method="GET",
            request_path="/api/v1/audit/compliance-pack",
            details={
                "export_type": "compliance_pack",
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "evidence_limit": int(evidence_limit),
            },
            success=True,
        )
        # Commit early so the export request is persisted even if bundle generation fails.
        await db.commit()
    except COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS as exc:
        logger.warning("compliance_pack_audit_log_failed", error=str(exc))
        await db.rollback()

    # --- Snapshot tenant-scoped settings (secrets/tokens redacted) ---
    notif_snapshot, remediation_snapshot, identity_snapshot = (
        await collect_settings_snapshots(db=db, tenant_id=cast(UUID, actor.tenant_id))
    )

    # --- Integration acceptance evidence (audit-grade) ---
    accepted_event_types = [
        AuditEventType.INTEGRATION_TEST_SLACK.value,
        AuditEventType.INTEGRATION_TEST_JIRA.value,
        AuditEventType.INTEGRATION_TEST_TEAMS.value,
        AuditEventType.INTEGRATION_TEST_WORKFLOW.value,
        AuditEventType.INTEGRATION_TEST_SUITE.value,
    ]
    integration_evidence = await collect_integration_evidence(
        db=db,
        tenant_id=cast(UUID, actor.tenant_id),
        event_types=accepted_event_types,
        limit=int(evidence_limit),
    )

    payload_specs: tuple[tuple[str, str, str, bool], ...] = (
        (
            "acceptance_kpi_evidence",
            AuditEventType.ACCEPTANCE_KPIS_CAPTURED.value,
            "acceptance_kpis",
            True,
        ),
        (
            "leadership_kpi_evidence",
            AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
            "leadership_kpis",
            True,
        ),
        (
            "quarterly_commercial_proof_evidence",
            AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value,
            "quarterly_report",
            True,
        ),
        (
            "identity_smoke_evidence",
            AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED.value,
            "identity_smoke",
            False,
        ),
        (
            "sso_federation_validation_evidence",
            AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED.value,
            "sso_federation_validation",
            False,
        ),
        (
            "performance_load_test_evidence",
            AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value,
            "load_test",
            False,
        ),
        (
            "ingestion_persistence_benchmark_evidence",
            AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value,
            "benchmark",
            False,
        ),
        (
            "ingestion_soak_evidence",
            AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value,
            "ingestion_soak",
            False,
        ),
        (
            "partitioning_evidence",
            AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED.value,
            "partitioning",
            False,
        ),
        ("job_slo_evidence", AuditEventType.JOBS_SLO_CAPTURED.value, "job_slo", False),
        (
            "tenant_isolation_evidence",
            AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value,
            "tenant_isolation",
            False,
        ),
        (
            "carbon_assurance_evidence",
            AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value,
            "carbon_assurance",
            False,
        ),
    )
    payload_evidence = await collect_payload_evidence_map(
        db=db,
        tenant_id=cast(UUID, actor.tenant_id),
        evidence_limit=int(evidence_limit),
        payload_specs=payload_specs,
        collect_payload_evidence=collect_payload_evidence,
    )

    # --- Carbon factor lifecycle evidence (global, non-tenant data) ---
    carbon_factor_sets, carbon_factor_update_logs = (
        await collect_carbon_factor_evidence(db=db, limit=int(evidence_limit))
    )

    # --- Audit logs CSV export ---
    audit_query = (
        select(AuditLog)
        .where(AuditLog.tenant_id == actor.tenant_id)
        .order_by(desc(AuditLog.event_timestamp))
    )
    if start_date:
        audit_query = audit_query.where(AuditLog.event_timestamp >= start_date)
    if end_date:
        audit_query = audit_query.where(AuditLog.event_timestamp <= end_date)
    audit_query = audit_query.limit(10000)
    audit_rows = (await db.execute(audit_query)).scalars().all()

    audit_csv = io.StringIO()
    writer = csv.writer(audit_csv)
    writer.writerow(
        [
            "id",
            "event_type",
            "event_timestamp",
            "actor_email",
            "resource_type",
            "resource_id",
            "success",
            "correlation_id",
        ]
    )
    for row in audit_rows:
        writer.writerow(
            [
                str(row.id),
                sanitize_csv_cell(row.event_type),
                sanitize_csv_cell(row.event_timestamp.isoformat()),
                sanitize_csv_cell(row.actor_email or ""),
                sanitize_csv_cell(row.resource_type or ""),
                sanitize_csv_cell(str(row.resource_id) if row.resource_id else ""),
                sanitize_csv_cell(str(row.success)),
                sanitize_csv_cell(row.correlation_id or ""),
            ]
        )
    audit_csv.seek(0)

    reference_docs, included_doc_files = load_reference_documents()
    included_files: list[str] = default_included_files()
    (
        focus_export_info,
        savings_proof_info,
        realized_savings_info,
        close_package_info,
    ) = initialize_optional_export_state(
        include_focus_export=include_focus_export,
        focus_include_preliminary=focus_include_preliminary,
        focus_max_rows=int(focus_max_rows),
        include_savings_proof=include_savings_proof,
        include_realized_savings=include_realized_savings,
        realized_limit=int(realized_limit),
        include_close_package=include_close_package,
        close_enforce_finalized=close_enforce_finalized,
        close_max_restatements=int(close_max_restatements),
    )

    included_files.extend(included_doc_files)
    scope = resolve_optional_export_scopes(
        focus_export_info=focus_export_info,
        savings_proof_info=savings_proof_info,
        realized_savings_info=realized_savings_info,
        close_package_info=close_package_info,
        focus_provider=focus_provider,
        savings_provider=savings_provider,
        realized_provider=realized_provider,
        close_provider=close_provider,
        focus_start_date=focus_start_date,
        focus_end_date=focus_end_date,
        savings_start_date=savings_start_date,
        savings_end_date=savings_end_date,
        realized_start_date=realized_start_date,
        realized_end_date=realized_end_date,
        close_start_date=close_start_date,
        close_end_date=close_end_date,
        default_start_date=start_date,
        default_end_date=end_date,
        exported_at=exported_at,
    )
    normalized_focus_provider = scope["normalized_focus_provider"]
    normalized_savings_provider = scope["normalized_savings_provider"]
    normalized_realized_provider = scope["normalized_realized_provider"]
    normalized_close_provider = scope["normalized_close_provider"]
    focus_window_start = scope["focus_window_start"]
    focus_window_end = scope["focus_window_end"]
    savings_window_start = scope["savings_window_start"]
    savings_window_end = scope["savings_window_end"]
    realized_window_start = scope["realized_window_start"]
    realized_window_end = scope["realized_window_end"]
    close_window_start = scope["close_window_start"]
    close_window_end = scope["close_window_end"]

    manifest = build_manifest(
        exported_at=exported_at,
        run_id=run_id,
        actor=actor,
        app_environment=app_settings.ENVIRONMENT,
        app_version=app_settings.VERSION,
        start_date=start_date,
        end_date=end_date,
        evidence_limit=int(evidence_limit),
        included_files=included_files,
        focus_export_info=focus_export_info,
        savings_proof_info=savings_proof_info,
        close_package_info=close_package_info,
        leadership_kpi_evidence=payload_evidence["leadership_kpi_evidence"],
        quarterly_commercial_proof_evidence=payload_evidence[
            "quarterly_commercial_proof_evidence"
        ],
        identity_smoke_evidence=payload_evidence["identity_smoke_evidence"],
        sso_federation_validation_evidence=payload_evidence[
            "sso_federation_validation_evidence"
        ],
        performance_load_test_evidence=payload_evidence[
            "performance_load_test_evidence"
        ],
        ingestion_persistence_benchmark_evidence=payload_evidence[
            "ingestion_persistence_benchmark_evidence"
        ],
        ingestion_soak_evidence=payload_evidence["ingestion_soak_evidence"],
        partitioning_evidence=payload_evidence["partitioning_evidence"],
        job_slo_evidence=payload_evidence["job_slo_evidence"],
        tenant_isolation_evidence=payload_evidence["tenant_isolation_evidence"],
        carbon_assurance_evidence=payload_evidence["carbon_assurance_evidence"],
        carbon_factor_sets=carbon_factor_sets,
        carbon_factor_update_logs=carbon_factor_update_logs,
    )

    core_json_payloads: dict[str, Any] = {
        "notification_settings.json": notif_snapshot,
        "remediation_settings.json": remediation_snapshot,
        "identity_settings.json": identity_snapshot,
        "integration_acceptance_evidence.json": integration_evidence,
        "acceptance_kpis_evidence.json": payload_evidence["acceptance_kpi_evidence"],
        "leadership_kpis_evidence.json": payload_evidence["leadership_kpi_evidence"],
        "quarterly_commercial_proof_evidence.json": payload_evidence[
            "quarterly_commercial_proof_evidence"
        ],
        "identity_smoke_evidence.json": payload_evidence["identity_smoke_evidence"],
        "sso_federation_validation_evidence.json": payload_evidence[
            "sso_federation_validation_evidence"
        ],
        "performance_load_test_evidence.json": payload_evidence[
            "performance_load_test_evidence"
        ],
        "ingestion_persistence_benchmark_evidence.json": (
            payload_evidence["ingestion_persistence_benchmark_evidence"]
        ),
        "ingestion_soak_evidence.json": payload_evidence["ingestion_soak_evidence"],
        "partitioning_evidence.json": payload_evidence["partitioning_evidence"],
        "job_slo_evidence.json": payload_evidence["job_slo_evidence"],
        "tenant_isolation_evidence.json": payload_evidence["tenant_isolation_evidence"],
        "carbon_assurance_evidence.json": payload_evidence["carbon_assurance_evidence"],
        "carbon_factor_sets.json": carbon_factor_sets,
        "carbon_factor_update_logs.json": carbon_factor_update_logs,
    }
    doc_payloads = build_doc_payloads(reference_docs)

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        write_core_artifacts(
            zf=zf,
            audit_csv=audit_csv,
            json_payloads=core_json_payloads,
            doc_payloads=doc_payloads,
        )

        await run_focus_export(
            zf=zf,
            db=db,
            actor=actor,
            include_focus_export=include_focus_export,
            included_files=included_files,
            focus_export_info=focus_export_info,
            focus_window_start=focus_window_start,
            focus_window_end=focus_window_end,
            normalized_focus_provider=normalized_focus_provider,
            focus_include_preliminary=focus_include_preliminary,
            focus_max_rows=int(focus_max_rows),
            sanitize_csv_cell=sanitize_csv_cell,
            recoverable_errors=COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS,
        )
        await run_savings_proof_export(
            zf=zf,
            db=db,
            actor=actor,
            include_savings_proof=include_savings_proof,
            included_files=included_files,
            savings_proof_info=savings_proof_info,
            savings_window_start=savings_window_start,
            savings_window_end=savings_window_end,
            normalized_savings_provider=normalized_savings_provider,
            recoverable_errors=COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS,
        )
        await run_realized_savings_export(
            zf=zf,
            db=db,
            actor=actor,
            include_realized_savings=include_realized_savings,
            included_files=included_files,
            realized_savings_info=realized_savings_info,
            realized_window_start=realized_window_start,
            realized_window_end=realized_window_end,
            normalized_realized_provider=normalized_realized_provider,
            realized_limit=int(realized_limit),
            recoverable_errors=COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS,
        )
        await run_close_package_export(
            zf=zf,
            db=db,
            actor=actor,
            include_close_package=include_close_package,
            included_files=included_files,
            close_package_info=close_package_info,
            close_window_start=close_window_start,
            close_window_end=close_window_end,
            normalized_close_provider=normalized_close_provider,
            close_enforce_finalized=bool(close_enforce_finalized),
            close_max_restatements=int(close_max_restatements),
            recoverable_errors=COMPLIANCE_PACK_BUNDLE_RECOVERABLE_ERRORS,
        )

        if "manifest.json" not in included_files:
            included_files.insert(0, "manifest.json")
        manifest["included_files"] = included_files
        manifest["focus_export"] = focus_export_info
        manifest["savings_proof"] = savings_proof_info
        manifest["realized_savings"] = realized_savings_info
        manifest["close_package"] = close_package_info
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    bundle.seek(0)

    filename = (
        f"compliance-pack-{actor.tenant_id}-{exported_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return CompliancePackBundleResult(body=bundle.getvalue(), filename=filename)
