from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional, cast
from uuid import UUID, uuid4

import csv
import io
import json
import zipfile
import structlog
from fastapi import HTTPException
from fastapi.responses import Response
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
from app.modules.governance.domain.security.compliance_pack_support import (
    load_reference_documents,
    normalize_optional_provider,
    resolve_window,
)
from app.modules.governance.domain.security.compliance_pack_bundle_exports import (
    build_manifest,
    run_close_package_export,
    run_focus_export,
    run_realized_savings_export,
    run_savings_proof_export,
    write_core_artifacts,
)
from app.shared.core.auth import CurrentUser
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
    user: CurrentUser,
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
) -> Response:
    exported_at = datetime.now(timezone.utc)
    run_id = str(uuid4())
    app_settings = get_settings()

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    # Record the export request (SOC2 evidence: export access is auditable).
    try:
        audit_logger = AuditLogger(
            db, cast(UUID, user.tenant_id), correlation_id=run_id
        )
        await audit_logger.log(
            event_type=AuditEventType.EXPORT_REQUESTED,
            actor_id=user.id,
            actor_email=user.email,
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
        await collect_settings_snapshots(db=db, tenant_id=cast(UUID, user.tenant_id))
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
        tenant_id=cast(UUID, user.tenant_id),
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
    payload_evidence: dict[str, list[dict[str, Any]]] = {}
    for key, event_type, payload_key, include_thresholds in payload_specs:
        payload_evidence[key] = await collect_payload_evidence(
            db=db,
            tenant_id=cast(UUID, user.tenant_id),
            event_type=event_type,
            payload_key=payload_key,
            limit=int(evidence_limit),
            include_thresholds=include_thresholds,
        )

    acceptance_kpi_evidence = payload_evidence["acceptance_kpi_evidence"]
    leadership_kpi_evidence = payload_evidence["leadership_kpi_evidence"]
    quarterly_commercial_proof_evidence = payload_evidence[
        "quarterly_commercial_proof_evidence"
    ]
    identity_smoke_evidence = payload_evidence["identity_smoke_evidence"]
    sso_federation_validation_evidence = payload_evidence[
        "sso_federation_validation_evidence"
    ]
    performance_load_test_evidence = payload_evidence["performance_load_test_evidence"]
    ingestion_persistence_benchmark_evidence = payload_evidence[
        "ingestion_persistence_benchmark_evidence"
    ]
    ingestion_soak_evidence = payload_evidence["ingestion_soak_evidence"]
    partitioning_evidence = payload_evidence["partitioning_evidence"]
    job_slo_evidence = payload_evidence["job_slo_evidence"]
    tenant_isolation_evidence = payload_evidence["tenant_isolation_evidence"]
    carbon_assurance_evidence = payload_evidence["carbon_assurance_evidence"]

    # --- Carbon factor lifecycle evidence (global, non-tenant data) ---
    carbon_factor_sets, carbon_factor_update_logs = (
        await collect_carbon_factor_evidence(db=db, limit=int(evidence_limit))
    )

    # --- Audit logs CSV export ---
    audit_query = (
        select(AuditLog)
        .where(AuditLog.tenant_id == user.tenant_id)
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
    scim_doc = reference_docs.get("scim_doc")
    idp_reference_doc = reference_docs.get("idp_reference_doc")
    sso_doc = reference_docs.get("sso_doc")
    teams_doc = reference_docs.get("teams_doc")
    compliance_pack_doc = reference_docs.get("compliance_pack_doc")
    focus_doc = reference_docs.get("focus_doc")
    acceptance_doc = reference_docs.get("acceptance_doc")
    close_runbook_doc = reference_docs.get("close_runbook_doc")
    tenant_lifecycle_doc = reference_docs.get("tenant_lifecycle_doc")
    partition_maintenance_doc = reference_docs.get("partition_maintenance_doc")
    licensing_doc = reference_docs.get("licensing_doc")
    license_text = reference_docs.get("license_text")
    trademark_policy_doc = reference_docs.get("trademark_policy_doc")
    commercial_license_doc = reference_docs.get("commercial_license_doc")

    included_files: list[str] = [
        "audit_logs.csv",
        "notification_settings.json",
        "remediation_settings.json",
        "identity_settings.json",
        "integration_acceptance_evidence.json",
        "acceptance_kpis_evidence.json",
        "leadership_kpis_evidence.json",
        "quarterly_commercial_proof_evidence.json",
        "identity_smoke_evidence.json",
        "sso_federation_validation_evidence.json",
        "performance_load_test_evidence.json",
        "ingestion_persistence_benchmark_evidence.json",
        "ingestion_soak_evidence.json",
        "partitioning_evidence.json",
        "job_slo_evidence.json",
        "tenant_isolation_evidence.json",
        "carbon_assurance_evidence.json",
        "carbon_factor_sets.json",
        "carbon_factor_update_logs.json",
    ]
    focus_export_info: dict[str, Any] = {
        "included": bool(include_focus_export),
        "provider": None,
        "include_preliminary": bool(focus_include_preliminary),
        "max_rows": int(focus_max_rows),
        "rows_written": 0,
        "truncated": False,
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_focus_export else "pending",
        "error": None,
    }
    savings_proof_info: dict[str, Any] = {
        "included": bool(include_savings_proof),
        "provider": None,
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_savings_proof else "pending",
        "error": None,
    }
    realized_savings_info: dict[str, Any] = {
        "included": bool(include_realized_savings),
        "provider": None,
        "limit": int(realized_limit),
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_realized_savings else "pending",
        "error": None,
        "rows_written": 0,
    }
    close_package_info: dict[str, Any] = {
        "included": bool(include_close_package),
        "provider": None,
        "enforce_finalized": bool(close_enforce_finalized),
        "max_restatements": int(close_max_restatements),
        "window": {
            "start_date": None,
            "end_date": None,
        },
        "status": "skipped" if not include_close_package else "pending",
        "error": None,
    }

    included_files.extend(included_doc_files)

    normalized_focus_provider = normalize_optional_provider(
        provider=focus_provider,
        provider_name="focus_provider",
    )
    focus_export_info["provider"] = normalized_focus_provider

    focus_window_start, focus_window_end = resolve_window(
        start=focus_start_date,
        end=focus_end_date,
        default_start=(start_date or (exported_at - timedelta(days=30))).date(),
        default_end=(end_date or exported_at).date(),
        error_detail="start_date must be <= end_date",
    )
    focus_export_info["window"] = {
        "start_date": focus_window_start.isoformat(),
        "end_date": focus_window_end.isoformat(),
    }

    # Savings Proof window/provider validation
    normalized_savings_provider = normalize_optional_provider(
        provider=savings_provider,
        provider_name="savings_provider",
    )
    savings_window_start, savings_window_end = resolve_window(
        start=savings_start_date,
        end=savings_end_date,
        default_start=focus_window_start,
        default_end=focus_window_end,
        error_detail="savings_start_date must be <= savings_end_date",
    )
    savings_proof_info["provider"] = normalized_savings_provider
    savings_proof_info["window"] = {
        "start_date": savings_window_start.isoformat(),
        "end_date": savings_window_end.isoformat(),
    }

    # Realized savings evidence window/provider validation (executed_at window)
    normalized_realized_provider = normalize_optional_provider(
        provider=realized_provider,
        provider_name="realized_provider",
    )
    realized_window_start, realized_window_end = resolve_window(
        start=realized_start_date,
        end=realized_end_date,
        default_start=savings_window_start,
        default_end=savings_window_end,
        error_detail="realized_start_date must be <= realized_end_date",
    )
    realized_savings_info["provider"] = normalized_realized_provider
    realized_savings_info["window"] = {
        "start_date": realized_window_start.isoformat(),
        "end_date": realized_window_end.isoformat(),
    }

    # Close package window/provider validation
    normalized_close_provider = normalize_optional_provider(
        provider=close_provider,
        provider_name="close_provider",
    )
    close_window_start, close_window_end = resolve_window(
        start=close_start_date,
        end=close_end_date,
        default_start=focus_window_start,
        default_end=focus_window_end,
        error_detail="close_start_date must be <= close_end_date",
    )
    close_package_info["provider"] = normalized_close_provider
    close_package_info["window"] = {
        "start_date": close_window_start.isoformat(),
        "end_date": close_window_end.isoformat(),
    }

    manifest = build_manifest(
        exported_at=exported_at,
        run_id=run_id,
        user=user,
        app_environment=app_settings.ENVIRONMENT,
        app_version=app_settings.VERSION,
        start_date=start_date,
        end_date=end_date,
        evidence_limit=int(evidence_limit),
        included_files=included_files,
        focus_export_info=focus_export_info,
        savings_proof_info=savings_proof_info,
        close_package_info=close_package_info,
        leadership_kpi_evidence=leadership_kpi_evidence,
        quarterly_commercial_proof_evidence=quarterly_commercial_proof_evidence,
        identity_smoke_evidence=identity_smoke_evidence,
        sso_federation_validation_evidence=sso_federation_validation_evidence,
        performance_load_test_evidence=performance_load_test_evidence,
        ingestion_persistence_benchmark_evidence=ingestion_persistence_benchmark_evidence,
        ingestion_soak_evidence=ingestion_soak_evidence,
        partitioning_evidence=partitioning_evidence,
        job_slo_evidence=job_slo_evidence,
        tenant_isolation_evidence=tenant_isolation_evidence,
        carbon_assurance_evidence=carbon_assurance_evidence,
        carbon_factor_sets=carbon_factor_sets,
        carbon_factor_update_logs=carbon_factor_update_logs,
    )

    core_json_payloads: dict[str, Any] = {
        "notification_settings.json": notif_snapshot,
        "remediation_settings.json": remediation_snapshot,
        "identity_settings.json": identity_snapshot,
        "integration_acceptance_evidence.json": integration_evidence,
        "acceptance_kpis_evidence.json": acceptance_kpi_evidence,
        "leadership_kpis_evidence.json": leadership_kpi_evidence,
        "quarterly_commercial_proof_evidence.json": quarterly_commercial_proof_evidence,
        "identity_smoke_evidence.json": identity_smoke_evidence,
        "sso_federation_validation_evidence.json": sso_federation_validation_evidence,
        "performance_load_test_evidence.json": performance_load_test_evidence,
        "ingestion_persistence_benchmark_evidence.json": (
            ingestion_persistence_benchmark_evidence
        ),
        "ingestion_soak_evidence.json": ingestion_soak_evidence,
        "partitioning_evidence.json": partitioning_evidence,
        "job_slo_evidence.json": job_slo_evidence,
        "tenant_isolation_evidence.json": tenant_isolation_evidence,
        "carbon_assurance_evidence.json": carbon_assurance_evidence,
        "carbon_factor_sets.json": carbon_factor_sets,
        "carbon_factor_update_logs.json": carbon_factor_update_logs,
    }
    doc_payloads: dict[str, Optional[str]] = {
        "docs/integrations/scim.md": scim_doc,
        "docs/integrations/idp_reference_configs.md": idp_reference_doc,
        "docs/integrations/sso.md": sso_doc,
        "docs/integrations/microsoft_teams.md": teams_doc,
        "docs/compliance/compliance_pack.md": compliance_pack_doc,
        "docs/compliance/focus_export.md": focus_doc,
        "docs/ops/acceptance_evidence_capture.md": acceptance_doc,
        "docs/runbooks/month_end_close.md": close_runbook_doc,
        "docs/runbooks/tenant_data_lifecycle.md": tenant_lifecycle_doc,
        "docs/runbooks/partition_maintenance.md": partition_maintenance_doc,
        "docs/licensing.md": licensing_doc,
        "LICENSE": license_text,
        "TRADEMARK_POLICY.md": trademark_policy_doc,
        "COMMERCIAL_LICENSE.md": commercial_license_doc,
    }

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
            user=user,
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
            user=user,
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
            user=user,
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
            user=user,
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
        f"compliance-pack-{user.tenant_id}-{exported_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
