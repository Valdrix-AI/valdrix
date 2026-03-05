from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.governance.domain.security.compliance_pack_bundle_exports import (
    build_manifest,
    run_focus_export,
    write_core_artifacts,
)


def test_build_manifest_tracks_counts_and_window() -> None:
    user = SimpleNamespace(tenant_id=uuid4(), id=uuid4(), email="ops@test.local")
    manifest = build_manifest(
        exported_at=datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc),
        run_id="run-1",
        user=user,  # type: ignore[arg-type]
        app_environment="test",
        app_version="1.2.3",
        start_date=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 28, 23, 59, tzinfo=timezone.utc),
        evidence_limit=50,
        included_files=["manifest.json", "audit_logs.csv"],
        focus_export_info={"status": "ok", "rows_written": 2},
        savings_proof_info={"status": "ok"},
        close_package_info={"status": "ok"},
        leadership_kpi_evidence=[{"kpi": 1}],
        quarterly_commercial_proof_evidence=[{"report": 1}, {"report": 2}],
        identity_smoke_evidence=[],
        sso_federation_validation_evidence=[{"ok": True}],
        performance_load_test_evidence=[],
        ingestion_persistence_benchmark_evidence=[],
        ingestion_soak_evidence=[],
        partitioning_evidence=[],
        job_slo_evidence=[],
        tenant_isolation_evidence=[],
        carbon_assurance_evidence=[],
        carbon_factor_sets=[{"set": 1}],
        carbon_factor_update_logs=[{"log": 1}],
    )

    assert manifest["run_id"] == "run-1"
    assert manifest["window"]["start_date"] == "2026-02-01T00:00:00+00:00"
    assert manifest["leadership_kpis"]["count"] == 1
    assert manifest["quarterly_commercial_proof_reports"]["count"] == 2
    assert manifest["carbon_factors"]["factor_sets_count"] == 1
    assert manifest["included_files"] == ["manifest.json", "audit_logs.csv"]


def test_write_core_artifacts_writes_json_and_docs() -> None:
    audit_csv = io.StringIO()
    audit_csv.write("id,event_type\n1,export\n")
    bundle = io.BytesIO()

    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        write_core_artifacts(
            zf=zf,
            audit_csv=audit_csv,
            json_payloads={"notification_settings.json": {"enabled": True}},
            doc_payloads={
                "docs/compliance/compliance_pack.md": "# pack",
                "docs/skip.md": None,
            },
        )

    with zipfile.ZipFile(io.BytesIO(bundle.getvalue()), mode="r") as zf:
        assert "audit_logs.csv" in zf.namelist()
        assert "notification_settings.json" in zf.namelist()
        assert "docs/compliance/compliance_pack.md" in zf.namelist()
        assert "docs/skip.md" not in zf.namelist()
        payload = json.loads(zf.read("notification_settings.json").decode("utf-8"))
        assert payload["enabled"] is True


@pytest.mark.asyncio
async def test_run_focus_export_skips_when_disabled() -> None:
    info = {"status": "skipped", "rows_written": 0, "truncated": False, "error": None}
    bundle = io.BytesIO()
    with zipfile.ZipFile(bundle, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        await run_focus_export(
            zf=zf,
            db=SimpleNamespace(),  # type: ignore[arg-type]
            user=SimpleNamespace(tenant_id=uuid4()),  # type: ignore[arg-type]
            include_focus_export=False,
            included_files=[],
            focus_export_info=info,
            focus_window_start=date(2026, 2, 1),
            focus_window_end=date(2026, 2, 28),
            normalized_focus_provider=None,
            focus_include_preliminary=False,
            focus_max_rows=100,
            sanitize_csv_cell=lambda value: str(value),
            recoverable_errors=(RuntimeError, ValueError),
        )
    assert info["status"] == "skipped"
