from datetime import date, datetime, time, timezone
from typing import Any, Callable, Optional, cast
from uuid import UUID

import csv
import io
import json
import zipfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.auth import CurrentUser


def _append_unique(paths: list[str], path: str) -> None:
    if path not in paths:
        paths.append(path)


def write_core_artifacts(
    *,
    zf: zipfile.ZipFile,
    audit_csv: io.StringIO,
    json_payloads: dict[str, Any],
    doc_payloads: dict[str, Optional[str]],
) -> None:
    zf.writestr("audit_logs.csv", audit_csv.getvalue())
    for path, payload in json_payloads.items():
        zf.writestr(path, json.dumps(payload, indent=2, sort_keys=True))
    for path, content in doc_payloads.items():
        if content is not None:
            zf.writestr(path, content)


def build_manifest(
    *,
    exported_at: datetime,
    run_id: str,
    user: CurrentUser,
    app_environment: str,
    app_version: str,
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    evidence_limit: int,
    included_files: list[str],
    focus_export_info: dict[str, Any],
    savings_proof_info: dict[str, Any],
    close_package_info: dict[str, Any],
    leadership_kpi_evidence: list[dict[str, Any]],
    quarterly_commercial_proof_evidence: list[dict[str, Any]],
    identity_smoke_evidence: list[dict[str, Any]],
    sso_federation_validation_evidence: list[dict[str, Any]],
    performance_load_test_evidence: list[dict[str, Any]],
    ingestion_persistence_benchmark_evidence: list[dict[str, Any]],
    ingestion_soak_evidence: list[dict[str, Any]],
    partitioning_evidence: list[dict[str, Any]],
    job_slo_evidence: list[dict[str, Any]],
    tenant_isolation_evidence: list[dict[str, Any]],
    carbon_assurance_evidence: list[dict[str, Any]],
    carbon_factor_sets: list[dict[str, Any]],
    carbon_factor_update_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "exported_at": exported_at.isoformat(),
        "run_id": run_id,
        "tenant_id": str(user.tenant_id),
        "actor_id": str(user.id),
        "actor_email": user.email,
        "environment": app_environment,
        "app_version": app_version,
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


async def run_focus_export(
    *,
    zf: zipfile.ZipFile,
    db: AsyncSession,
    user: CurrentUser,
    include_focus_export: bool,
    included_files: list[str],
    focus_export_info: dict[str, Any],
    focus_window_start: date,
    focus_window_end: date,
    normalized_focus_provider: Optional[str],
    focus_include_preliminary: bool,
    focus_max_rows: int,
    sanitize_csv_cell: Callable[[Any], str],
    recoverable_errors: tuple[type[Exception], ...],
) -> None:
    if not include_focus_export:
        return
    try:
        from app.modules.reporting.domain.focus_export import (
            FOCUS_V13_CORE_COLUMNS,
            FocusV13ExportService,
        )

        export_service = FocusV13ExportService(db)
        rows_written = 0
        truncated = False

        with zf.open("exports/focus-v1.3-core.csv", "w") as fp:
            _append_unique(included_files, "exports/focus-v1.3-core.csv")
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
    except recoverable_errors as exc:
        focus_export_info.update({"status": "error", "error": str(exc)})
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
        _append_unique(included_files, "exports/focus-v1.3-core.error.json")


async def run_savings_proof_export(
    *,
    zf: zipfile.ZipFile,
    db: AsyncSession,
    user: CurrentUser,
    include_savings_proof: bool,
    included_files: list[str],
    savings_proof_info: dict[str, Any],
    savings_window_start: date,
    savings_window_end: date,
    normalized_savings_provider: Optional[str],
    recoverable_errors: tuple[type[Exception], ...],
) -> None:
    if not include_savings_proof:
        return
    try:
        from app.modules.reporting.domain.savings_proof import SavingsProofService

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
        _append_unique(included_files, json_path)
        _append_unique(included_files, csv_path)
        zf.writestr(
            json_path,
            json.dumps(payload.model_dump(), indent=2, sort_keys=True),
        )
        zf.writestr(csv_path, SavingsProofService.render_csv(payload))

        drilldowns: list[tuple[str, str]] = [
            ("strategy_type", "strategy-type"),
            ("remediation_action", "remediation-action"),
        ]
        for dimension, slug in drilldowns:
            drill_json_path = f"exports/savings-proof-drilldown-{slug}.json"
            drill_csv_path = f"exports/savings-proof-drilldown-{slug}.csv"
            _append_unique(included_files, drill_json_path)
            _append_unique(included_files, drill_csv_path)

            drill_payload = await service.drilldown(
                tenant_id=cast(UUID, user.tenant_id),
                tier=str(getattr(user, "tier", "")),
                start_date=savings_window_start,
                end_date=savings_window_end,
                provider=normalized_savings_provider,
                dimension=dimension,
                limit=200,
            )
            zf.writestr(
                drill_json_path,
                json.dumps(drill_payload.model_dump(), indent=2, sort_keys=True),
            )
            zf.writestr(
                drill_csv_path,
                SavingsProofService.render_drilldown_csv(drill_payload),
            )
        savings_proof_info.update({"status": "ok"})
    except recoverable_errors as exc:
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
        _append_unique(included_files, error_path)


async def run_realized_savings_export(
    *,
    zf: zipfile.ZipFile,
    db: AsyncSession,
    user: CurrentUser,
    include_realized_savings: bool,
    included_files: list[str],
    realized_savings_info: dict[str, Any],
    realized_window_start: date,
    realized_window_end: date,
    normalized_realized_provider: Optional[str],
    realized_limit: int,
    recoverable_errors: tuple[type[Exception], ...],
) -> None:
    if not include_realized_savings:
        return
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
                RealizedSavingsEvent.remediation_request_id == RemediationRequest.id,
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
                    "account_id": str(event.account_id) if event.account_id else None,
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
        _append_unique(included_files, json_path)
        _append_unique(included_files, csv_path)
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
        realized_writer: csv.DictWriter[str] = csv.DictWriter(buf, fieldnames=fieldnames)
        realized_writer.writeheader()
        for item in items:
            realized_writer.writerow(item)
        zf.writestr(csv_path, buf.getvalue())
        realized_savings_info.update({"status": "ok", "rows_written": len(items)})
    except recoverable_errors as exc:
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
        _append_unique(included_files, error_path)


async def run_close_package_export(
    *,
    zf: zipfile.ZipFile,
    db: AsyncSession,
    user: CurrentUser,
    include_close_package: bool,
    included_files: list[str],
    close_package_info: dict[str, Any],
    close_window_start: date,
    close_window_end: date,
    normalized_close_provider: Optional[str],
    close_enforce_finalized: bool,
    close_max_restatements: int,
    recoverable_errors: tuple[type[Exception], ...],
) -> None:
    if not include_close_package:
        return
    try:
        from app.modules.reporting.domain.reconciliation import CostReconciliationService

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
        _append_unique(included_files, json_path)
        _append_unique(included_files, csv_path)
        zf.writestr(
            json_path,
            json.dumps(package, indent=2, sort_keys=True, default=str),
        )
        zf.writestr(csv_path, close_csv)
        close_package_info.update({"status": "ok"})
    except recoverable_errors as exc:
        close_package_info.update({"status": "error", "error": str(exc)})
        error_path = "exports/close-package.error.json"
        zf.writestr(
            error_path,
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "hint": (
                        "Use GET /api/v1/costs/reconciliation/close-package "
                        "for direct export."
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
        )
        _append_unique(included_files, error_path)
