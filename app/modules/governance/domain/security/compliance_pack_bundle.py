from datetime import date, datetime, time, timedelta, timezone
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
from app.shared.core.auth import CurrentUser
from app.shared.core.config import get_settings

logger = structlog.get_logger()


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
    except Exception as exc:
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

    # --- Acceptance KPI evidence snapshots (audit-grade) ---
    acceptance_kpi_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.ACCEPTANCE_KPIS_CAPTURED.value,
        payload_key="acceptance_kpis",
        limit=int(evidence_limit),
        include_thresholds=True,
    )

    # --- Leadership KPI evidence snapshots (audit-grade) ---
    leadership_kpi_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
        payload_key="leadership_kpis",
        limit=int(evidence_limit),
        include_thresholds=True,
    )

    # --- Quarterly commercial proof report evidence snapshots (audit-grade) ---
    quarterly_commercial_proof_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value,
        payload_key="quarterly_report",
        limit=int(evidence_limit),
        include_thresholds=True,
    )

    # --- Identity IdP smoke-test evidence snapshots (audit-grade) ---
    identity_smoke_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED.value,
        payload_key="identity_smoke",
        limit=int(evidence_limit),
    )

    # --- SSO federation validation evidence snapshots (audit-grade) ---
    sso_federation_validation_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED.value,
        payload_key="sso_federation_validation",
        limit=int(evidence_limit),
    )

    # --- Performance load-test evidence snapshots (audit-grade) ---
    performance_load_test_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value,
        payload_key="load_test",
        limit=int(evidence_limit),
    )

    # --- Ingestion persistence benchmark evidence snapshots (audit-grade) ---
    ingestion_persistence_benchmark_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value,
        payload_key="benchmark",
        limit=int(evidence_limit),
    )

    # --- Ingestion soak evidence snapshots (audit-grade) ---
    ingestion_soak_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value,
        payload_key="ingestion_soak",
        limit=int(evidence_limit),
    )

    # --- Partitioning validation evidence snapshots (audit-grade) ---
    partitioning_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.PERFORMANCE_PARTITIONING_CAPTURED.value,
        payload_key="partitioning",
        limit=int(evidence_limit),
    )

    # --- Job SLO + backlog evidence snapshots (audit-grade) ---
    job_slo_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.JOBS_SLO_CAPTURED.value,
        payload_key="job_slo",
        limit=int(evidence_limit),
    )

    # --- Tenancy isolation verification evidence snapshots (audit-grade) ---
    tenant_isolation_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value,
        payload_key="tenant_isolation",
        limit=int(evidence_limit),
    )

    # --- Carbon assurance evidence snapshots (audit-grade) ---
    carbon_assurance_evidence = await collect_payload_evidence(
        db=db,
        tenant_id=cast(UUID, user.tenant_id),
        event_type=AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value,
        payload_key="carbon_assurance",
        limit=int(evidence_limit),
    )

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

    manifest = {
        "exported_at": exported_at.isoformat(),
        "run_id": run_id,
        "tenant_id": str(user.tenant_id),
        "actor_id": str(user.id),
        "actor_email": user.email,
        "environment": app_settings.ENVIRONMENT,
        "app_version": app_settings.VERSION,
        "window": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "focus_export": focus_export_info,
        "savings_proof": savings_proof_info,
        "close_package": close_package_info,
        "leadership_kpis": {
            "count": len(leadership_kpi_evidence),
            "limit": int(evidence_limit),
        },
        "quarterly_commercial_proof_reports": {
            "count": len(quarterly_commercial_proof_evidence),
            "limit": int(evidence_limit),
        },
        "identity_idp_smoke_tests": {
            "count": len(identity_smoke_evidence),
            "limit": int(evidence_limit),
        },
        "sso_federation_validation": {
            "count": len(sso_federation_validation_evidence),
            "limit": int(evidence_limit),
        },
        "performance_load_tests": {
            "count": len(performance_load_test_evidence),
            "limit": int(evidence_limit),
        },
        "ingestion_persistence_benchmarks": {
            "count": len(ingestion_persistence_benchmark_evidence),
            "limit": int(evidence_limit),
        },
        "ingestion_soak_runs": {
            "count": len(ingestion_soak_evidence),
            "limit": int(evidence_limit),
        },
        "partitioning_validation": {
            "count": len(partitioning_evidence),
            "limit": int(evidence_limit),
        },
        "job_slo_evidence": {
            "count": len(job_slo_evidence),
            "limit": int(evidence_limit),
        },
        "tenant_isolation_verifications": {
            "count": len(tenant_isolation_evidence),
            "limit": int(evidence_limit),
        },
        "carbon_assurance": {
            "count": len(carbon_assurance_evidence),
            "limit": int(evidence_limit),
        },
        "carbon_factors": {
            "factor_sets_count": len(carbon_factor_sets),
            "update_logs_count": len(carbon_factor_update_logs),
            "limit": int(evidence_limit),
        },
        "included_files": included_files,
        "notes": [
            "Secrets/tokens are redacted. Only boolean 'has_*' fields are included for encrypted credentials.",
            "Audit log export is capped at 10,000 records for performance.",
            "Bundled FOCUS export is bounded by focus_max_rows. Use /api/v1/costs/export/focus for full streaming export.",
            "Bundled Savings Proof prefers finance-grade realized savings evidence when available, otherwise falls back to estimated savings.",
            "Realized savings exports are bounded by realized_limit and filtered by executed_at window; missing rows usually indicate insufficient finalized ledger coverage for the baseline/measurement windows.",
            "Bundled close package restatement entries may be truncated via close_max_restatements.",
            "Carbon factor exports are global methodology artifacts (not tenant-scoped billing data).",
            "Key runbooks/licensing docs are included for procurement review under docs/.",
        ],
    }

    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("audit_logs.csv", audit_csv.getvalue())
        zf.writestr(
            "notification_settings.json",
            json.dumps(notif_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "remediation_settings.json",
            json.dumps(remediation_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "identity_settings.json",
            json.dumps(identity_snapshot, indent=2, sort_keys=True),
        )
        zf.writestr(
            "integration_acceptance_evidence.json",
            json.dumps(integration_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "acceptance_kpis_evidence.json",
            json.dumps(acceptance_kpi_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "leadership_kpis_evidence.json",
            json.dumps(leadership_kpi_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "quarterly_commercial_proof_evidence.json",
            json.dumps(quarterly_commercial_proof_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "identity_smoke_evidence.json",
            json.dumps(identity_smoke_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "sso_federation_validation_evidence.json",
            json.dumps(sso_federation_validation_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "performance_load_test_evidence.json",
            json.dumps(performance_load_test_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "ingestion_persistence_benchmark_evidence.json",
            json.dumps(
                ingestion_persistence_benchmark_evidence, indent=2, sort_keys=True
            ),
        )
        zf.writestr(
            "ingestion_soak_evidence.json",
            json.dumps(ingestion_soak_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "partitioning_evidence.json",
            json.dumps(partitioning_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "job_slo_evidence.json",
            json.dumps(job_slo_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "tenant_isolation_evidence.json",
            json.dumps(tenant_isolation_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_assurance_evidence.json",
            json.dumps(carbon_assurance_evidence, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_factor_sets.json",
            json.dumps(carbon_factor_sets, indent=2, sort_keys=True),
        )
        zf.writestr(
            "carbon_factor_update_logs.json",
            json.dumps(carbon_factor_update_logs, indent=2, sort_keys=True),
        )
        if scim_doc is not None:
            zf.writestr("docs/integrations/scim.md", scim_doc)
        if idp_reference_doc is not None:
            zf.writestr("docs/integrations/idp_reference_configs.md", idp_reference_doc)
        if sso_doc is not None:
            zf.writestr("docs/integrations/sso.md", sso_doc)
        if teams_doc is not None:
            zf.writestr("docs/integrations/microsoft_teams.md", teams_doc)
        if compliance_pack_doc is not None:
            zf.writestr("docs/compliance/compliance_pack.md", compliance_pack_doc)
        if focus_doc is not None:
            zf.writestr("docs/compliance/focus_export.md", focus_doc)
        if acceptance_doc is not None:
            zf.writestr("docs/ops/acceptance_evidence_capture.md", acceptance_doc)
        if close_runbook_doc is not None:
            zf.writestr("docs/runbooks/month_end_close.md", close_runbook_doc)
        if tenant_lifecycle_doc is not None:
            zf.writestr("docs/runbooks/tenant_data_lifecycle.md", tenant_lifecycle_doc)
        if partition_maintenance_doc is not None:
            zf.writestr(
                "docs/runbooks/partition_maintenance.md", partition_maintenance_doc
            )
        if licensing_doc is not None:
            zf.writestr("docs/licensing.md", licensing_doc)
        if license_text is not None:
            zf.writestr("LICENSE", license_text)
        if trademark_policy_doc is not None:
            zf.writestr("TRADEMARK_POLICY.md", trademark_policy_doc)
        if commercial_license_doc is not None:
            zf.writestr("COMMERCIAL_LICENSE.md", commercial_license_doc)

        if include_focus_export:
            try:
                from app.modules.reporting.domain.focus_export import (
                    FocusV13ExportService,
                    FOCUS_V13_CORE_COLUMNS,
                )

                export_service = FocusV13ExportService(db)
                rows_written = 0
                truncated = False

                with zf.open("exports/focus-v1.3-core.csv", "w") as fp:
                    if "exports/focus-v1.3-core.csv" not in included_files:
                        included_files.append("exports/focus-v1.3-core.csv")
                    text_fp = io.TextIOWrapper(fp, encoding="utf-8", newline="")
                    focus_writer = csv.writer(text_fp)
                    focus_writer.writerow(FOCUS_V13_CORE_COLUMNS)

                    async for focus_row in export_service.export_rows(
                        tenant_id=cast(UUID, user.tenant_id),
                        start_date=focus_window_start,
                        end_date=focus_window_end,
                        provider=normalized_focus_provider,
                        include_preliminary=bool(focus_include_preliminary),
                    ):
                        focus_row_dict = (
                            focus_row
                            if isinstance(focus_row, dict)
                            else dict(focus_row._mapping)
                            if hasattr(focus_row, "_mapping")
                            else {}
                        )
                        focus_writer.writerow(
                            [
                                sanitize_csv_cell(focus_row_dict.get(col, ""))
                                for col in FOCUS_V13_CORE_COLUMNS
                            ]
                        )
                        rows_written += 1
                        if rows_written % 1000 == 0:
                            text_fp.flush()
                        if rows_written >= int(focus_max_rows):
                            truncated = True
                            break
                    text_fp.flush()

                focus_export_info.update(
                    {
                        "rows_written": rows_written,
                        "truncated": truncated,
                        "status": "ok",
                    }
                )
            except Exception as exc:
                focus_export_info.update(
                    {
                        "status": "error",
                        "error": str(exc),
                    }
                )
                # Keep the pack usable even if the export fails.
                zf.writestr(
                    "exports/focus-v1.3-core.error.json",
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/costs/export/focus for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                # Ensure manifest lists the error artifact.
                if "exports/focus-v1.3-core.error.json" not in included_files:
                    included_files.append("exports/focus-v1.3-core.error.json")

        if include_savings_proof:
            try:
                from app.modules.reporting.domain.savings_proof import (
                    SavingsProofService,
                )

                service = SavingsProofService(db)
                payload = await service.generate(
                    tenant_id=cast(UUID, user.tenant_id),
                    tier=str(getattr(user, "tier", "")),
                    start_date=savings_window_start,
                    end_date=savings_window_end,
                    provider=normalized_savings_provider,
                )
                json_path = "exports/savings-proof.json"
                csv_path = "exports/savings-proof.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)
                zf.writestr(
                    json_path,
                    json.dumps(payload.model_dump(), indent=2, sort_keys=True),
                )
                zf.writestr(csv_path, SavingsProofService.render_csv(payload))

                # Drilldowns (Commercial proof v3): strategy type and remediation action.
                drilldowns: list[tuple[str, str]] = [
                    ("strategy_type", "strategy-type"),
                    ("remediation_action", "remediation-action"),
                ]
                for dim, dim_slug in drilldowns:
                    drill_json_path = f"exports/savings-proof-drilldown-{dim_slug}.json"
                    drill_csv_path = f"exports/savings-proof-drilldown-{dim_slug}.csv"
                    if drill_json_path not in included_files:
                        included_files.append(drill_json_path)
                    if drill_csv_path not in included_files:
                        included_files.append(drill_csv_path)

                    drill_payload = await service.drilldown(
                        tenant_id=cast(UUID, user.tenant_id),
                        tier=str(getattr(user, "tier", "")),
                        start_date=savings_window_start,
                        end_date=savings_window_end,
                        provider=normalized_savings_provider,
                        dimension=dim,
                        limit=200,
                    )
                    zf.writestr(
                        drill_json_path,
                        json.dumps(
                            drill_payload.model_dump(), indent=2, sort_keys=True
                        ),
                    )
                    zf.writestr(
                        drill_csv_path,
                        SavingsProofService.render_drilldown_csv(drill_payload),
                    )

                savings_proof_info.update({"status": "ok"})
            except Exception as exc:
                savings_proof_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/savings-proof.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/savings/proof for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        if include_realized_savings:
            try:
                from app.models.realized_savings import RealizedSavingsEvent
                from app.models.remediation import RemediationRequest

                realized_start_dt = datetime.combine(
                    realized_window_start, time.min, tzinfo=timezone.utc
                )
                realized_end_dt = datetime.combine(
                    realized_window_end, time.max, tzinfo=timezone.utc
                )

                realized_stmt = (
                    select(RealizedSavingsEvent, RemediationRequest.executed_at)
                    .join(
                        RemediationRequest,
                        RealizedSavingsEvent.remediation_request_id
                        == RemediationRequest.id,
                    )
                    .where(
                        RealizedSavingsEvent.tenant_id == user.tenant_id,
                        RemediationRequest.executed_at.is_not(None),
                        RemediationRequest.executed_at >= realized_start_dt,
                        RemediationRequest.executed_at <= realized_end_dt,
                    )
                    .order_by(RealizedSavingsEvent.computed_at.desc())
                    .limit(int(realized_limit))
                )
                if normalized_realized_provider:
                    realized_stmt = realized_stmt.where(
                        RealizedSavingsEvent.provider == normalized_realized_provider
                    )

                rows = list((await db.execute(realized_stmt)).all())
                items: list[dict[str, Any]] = []
                for event, executed_at in rows:
                    items.append(
                        {
                            "remediation_request_id": str(event.remediation_request_id),
                            "provider": str(event.provider),
                            "account_id": str(event.account_id)
                            if event.account_id
                            else None,
                            "resource_id": str(event.resource_id)
                            if event.resource_id
                            else None,
                            "region": str(event.region) if event.region else None,
                            "method": str(event.method),
                            "executed_at": executed_at.isoformat()
                            if isinstance(executed_at, datetime)
                            else None,
                            "baseline_start_date": event.baseline_start_date.isoformat(),
                            "baseline_end_date": event.baseline_end_date.isoformat(),
                            "measurement_start_date": event.measurement_start_date.isoformat(),
                            "measurement_end_date": event.measurement_end_date.isoformat(),
                            "baseline_avg_daily_cost_usd": float(
                                event.baseline_avg_daily_cost_usd or 0
                            ),
                            "measurement_avg_daily_cost_usd": float(
                                event.measurement_avg_daily_cost_usd or 0
                            ),
                            "realized_monthly_savings_usd": float(
                                event.realized_monthly_savings_usd or 0
                            ),
                            "confidence_score": float(event.confidence_score)
                            if event.confidence_score is not None
                            else None,
                            "computed_at": event.computed_at.isoformat(),
                        }
                    )

                json_path = "exports/realized-savings.json"
                csv_path = "exports/realized-savings.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)

                zf.writestr(json_path, json.dumps(items, indent=2, sort_keys=True))

                fieldnames = [
                    "remediation_request_id",
                    "provider",
                    "account_id",
                    "resource_id",
                    "region",
                    "method",
                    "executed_at",
                    "baseline_start_date",
                    "baseline_end_date",
                    "measurement_start_date",
                    "measurement_end_date",
                    "baseline_avg_daily_cost_usd",
                    "measurement_avg_daily_cost_usd",
                    "realized_monthly_savings_usd",
                    "confidence_score",
                    "computed_at",
                ]
                buf = io.StringIO()
                realized_csv_writer: csv.DictWriter[str] = csv.DictWriter(
                    buf, fieldnames=fieldnames
                )
                realized_csv_writer.writeheader()
                for item in items:
                    realized_csv_writer.writerow(item)
                zf.writestr(csv_path, buf.getvalue())

                realized_savings_info.update(
                    {"status": "ok", "rows_written": len(items)}
                )
            except Exception as exc:
                realized_savings_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/realized-savings.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/savings/realized/events for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        if include_close_package:
            try:
                from app.modules.reporting.domain.reconciliation import (
                    CostReconciliationService,
                )

                close_service = CostReconciliationService(db)
                package = await close_service.generate_close_package(
                    tenant_id=cast(UUID, user.tenant_id),
                    start_date=close_window_start,
                    end_date=close_window_end,
                    enforce_finalized=bool(close_enforce_finalized),
                    provider=normalized_close_provider,
                    max_restatement_entries=int(close_max_restatements),
                )
                close_csv = package.pop("csv", "")
                json_path = "exports/close-package.json"
                csv_path = "exports/close-package.csv"
                if json_path not in included_files:
                    included_files.append(json_path)
                if csv_path not in included_files:
                    included_files.append(csv_path)
                zf.writestr(
                    json_path,
                    json.dumps(package, indent=2, sort_keys=True, default=str),
                )
                zf.writestr(csv_path, close_csv)
                close_package_info.update({"status": "ok"})
            except Exception as exc:
                close_package_info.update({"status": "error", "error": str(exc)})
                error_path = "exports/close-package.error.json"
                zf.writestr(
                    error_path,
                    json.dumps(
                        {
                            "status": "error",
                            "error": str(exc),
                            "hint": "Use GET /api/v1/costs/reconciliation/close-package for direct export.",
                        },
                        indent=2,
                        sort_keys=True,
                    ),
                )
                if error_path not in included_files:
                    included_files.append(error_path)

        # Write manifest last so it can include bundled export stats.
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
