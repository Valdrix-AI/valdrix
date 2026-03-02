"""
Capture acceptance evidence artifacts for operator sign-off.

This script is intentionally "operator-safe":
- It never writes bearer tokens to disk.
- It redacts common secret keys from JSON artifacts.
- It produces a timestamped bundle under reports/acceptance/ (gitignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from app.shared.core.evidence_capture import redact_secrets, sanitize_bearer_token


def _ensure_test_env_for_in_process() -> None:
    # Set a minimal, deterministic test environment so in-process evidence capture can run
    # without requiring a live DB/server. Values are safe and non-secret.
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("DB_SSL_MODE", "disable")
    os.environ.setdefault(
        "SUPABASE_JWT_SECRET", "test-jwt-secret-for-testing-at-least-32-bytes"
    )
    os.environ.setdefault("ENCRYPTION_KEY", "32-byte-long-test-encryption-key")
    os.environ.setdefault("CSRF_SECRET_KEY", "test-csrf-secret-key-at-least-32-bytes")
    os.environ.setdefault(
        "KDF_SALT",
        "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=",
    )


async def _bootstrap_in_process_app_and_token() -> tuple[httpx.ASGITransport, str]:
    """
    Boot a local app instance and seed a minimal tenant+admin for evidence capture.

    This mode is intended for local dev/CI validation when a live environment is unavailable.
    """
    _ensure_test_env_for_in_process()

    # Use a file-backed sqlite DB so multiple connections share the same state.
    sqlite_path = Path("/tmp/valdrics_acceptance_capture.sqlite")
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{sqlite_path}")

    # Import after env is set.
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from contextlib import suppress

    from app.shared.db.base import Base
    from app.shared.db.session import engine as async_engine

    # Register models referenced by relationships.
    import app.models.cloud  # noqa: F401
    import app.models.tenant  # noqa: F401
    import app.models.tenant_identity_settings  # noqa: F401
    import app.models.notification_settings  # noqa: F401
    import app.models.remediation_settings  # noqa: F401
    import app.models.background_job  # noqa: F401
    import app.models.llm  # noqa: F401
    import app.modules.governance.domain.security.audit_log  # noqa: F401

    # Some environments (notably certain Python/aiosqlite builds) can fail to wake the event loop
    # for thread-safe callbacks unless there is at least one scheduled timer.
    # This keeps the loop responsive during sqlite bootstrap and avoids rare deadlocks/hangs.
    stop_wakeup = asyncio.Event()

    async def _wakeup_loop() -> None:
        while not stop_wakeup.is_set():
            await asyncio.sleep(0.2)

    wakeup_task = asyncio.create_task(_wakeup_loop())

    try:
        # Create tables
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        from app.models.tenant import Tenant, User, UserRole
        from app.shared.core.auth import create_access_token

        from uuid import UUID

        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
        user_id = UUID("00000000-0000-0000-0000-000000000002")
        email = "admin@valdrics.local"

        session_maker = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )
        async with session_maker() as db:
            # Seed tenant/user idempotently.
            tenant = await db.get(Tenant, tenant_id)
            if tenant is None:
                db.add(
                    Tenant(
                        id=tenant_id,
                        name="Acceptance Evidence Tenant",
                        plan="enterprise",
                    )
                )
            user = await db.get(User, user_id)
            if user is None:
                db.add(
                    User(
                        id=user_id,
                        email=email,
                        tenant_id=tenant_id,
                        role=UserRole.ADMIN.value,
                    )
                )
            await db.commit()

        token = create_access_token(
            {"sub": str(user_id), "email": email}, timedelta(hours=2)
        )

        from app.main import app as valdrics_app

        return httpx.ASGITransport(app=valdrics_app), token
    finally:
        stop_wakeup.set()
        wakeup_task.cancel()
        with suppress(asyncio.CancelledError):
            await wakeup_task


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    _safe_mkdir(path.parent)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True))


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


@dataclass(frozen=True)
class CaptureResult:
    name: str
    path: str
    status_code: int | None
    ok: bool
    error: str | None = None


def _build_url(base_url: str, path: str) -> str:
    normalized_base = base_url if base_url.endswith("/") else base_url + "/"
    normalized_path = path[1:] if path.startswith("/") else path
    return urljoin(normalized_base, normalized_path)


def _normalize_base_url(raw: str) -> str:
    """
    Normalize a base URL for httpx/urljoin.

    Operators frequently set VALDRICS_API_URL as `127.0.0.1:8000` without a scheme.
    We accept that and infer a scheme:
    - localhost/127.0.0.1/0.0.0.0 -> http
    - everything else -> https
    """
    value = str(raw or "").strip()
    if not value:
        return ""
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return value
    if lowered.startswith(("localhost", "127.0.0.1", "0.0.0.0")):
        return f"http://{value}"
    return f"https://{value}"


def _require_valid_base_url(raw: str) -> str:
    normalized = _normalize_base_url(raw)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(
            f"Invalid --url '{raw}'. Provide a full http(s) URL like 'http://127.0.0.1:8000'."
        )
    return normalized


def _iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _default_start_end() -> tuple[date, date]:
    end = date.today()
    start = end - timedelta(days=30)
    return start, end


def _previous_full_month() -> tuple[date, date]:
    today = date.today()
    first_this_month = today.replace(day=1)
    prev_month_end = first_this_month - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    return prev_month_start, prev_month_end


async def capture_acceptance_evidence(
    *,
    base_url: str,
    token: str,
    output_root: Path,
    start_date: date,
    end_date: date,
    close_start_date: date,
    close_end_date: date,
    close_provider: str = "all",
    close_enforce_finalized: bool = False,
    timeout_seconds: float = 60.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[Path, list[CaptureResult]]:
    timestamp = _utc_now_compact()
    bundle_dir = output_root / timestamp
    _safe_mkdir(bundle_dir)

    headers = {"Authorization": f"Bearer {token}"}

    results: list[CaptureResult] = []

    def record(
        name: str,
        file_path: Path,
        status_code: int | None,
        ok: bool,
        error: str | None = None,
    ) -> None:
        results.append(
            CaptureResult(
                name=name,
                path=str(file_path.relative_to(output_root)),
                status_code=status_code,
                ok=ok,
                error=error,
            )
        )

    async with httpx.AsyncClient(
        timeout=timeout_seconds, headers=headers, transport=transport
    ) as client:
        # CSRF: some deployments enforce CSRF even for bearer-authenticated unsafe methods.
        # This is best-effort and only impacts POST/PUT/DELETE calls in this script.
        try:
            csrf_resp = await client.get(_build_url(base_url, "/api/v1/public/csrf"))
            if csrf_resp.is_success:
                token_value = (csrf_resp.json() or {}).get("csrf_token")
                if token_value:
                    client.headers["X-CSRF-Token"] = str(token_value)
        except Exception:
            # Evidence capture should not fail just because CSRF bootstrap failed.
            pass

        # 1) Acceptance KPIs JSON
        kpi_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "json",
            }
        )
        kpis_url = _build_url(base_url, f"/api/v1/costs/acceptance/kpis?{kpi_query}")
        kpis_path = bundle_dir / "acceptance_kpis.json"
        try:
            resp = await client.get(kpis_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(kpis_path, payload)
                record("acceptance_kpis_json", kpis_path, resp.status_code, True)
            else:
                record(
                    "acceptance_kpis_json",
                    kpis_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("acceptance_kpis_json", kpis_path, None, False, _format_exception(exc))

        # 2) Acceptance KPIs CSV
        kpi_csv_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "csv",
            }
        )
        kpis_csv_url = _build_url(
            base_url, f"/api/v1/costs/acceptance/kpis?{kpi_csv_query}"
        )
        kpis_csv_path = bundle_dir / "acceptance_kpis.csv"
        try:
            resp = await client.get(kpis_csv_url)
            if resp.is_success:
                _write_text(kpis_csv_path, resp.text)
                record("acceptance_kpis_csv", kpis_csv_path, resp.status_code, True)
            else:
                record(
                    "acceptance_kpis_csv",
                    kpis_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("acceptance_kpis_csv", kpis_csv_path, None, False, _format_exception(exc))

        # 2b) Leadership KPIs export (JSON + CSV) (best-effort; depends on tier/features)
        leadership_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "json",
            }
        )
        leadership_url = _build_url(
            base_url, f"/api/v1/leadership/kpis?{leadership_query}"
        )
        leadership_path = bundle_dir / "leadership_kpis.json"
        try:
            resp = await client.get(leadership_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(leadership_path, payload)
                record("leadership_kpis_json", leadership_path, resp.status_code, True)
            else:
                record(
                    "leadership_kpis_json",
                    leadership_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("leadership_kpis_json", leadership_path, None, False, _format_exception(exc))

        leadership_csv_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "csv",
            }
        )
        leadership_csv_url = _build_url(
            base_url, f"/api/v1/leadership/kpis?{leadership_csv_query}"
        )
        leadership_csv_path = bundle_dir / "leadership_kpis.csv"
        try:
            resp = await client.get(leadership_csv_url)
            if resp.is_success:
                _write_text(leadership_csv_path, resp.text)
                record(
                    "leadership_kpis_csv", leadership_csv_path, resp.status_code, True
                )
            else:
                record(
                    "leadership_kpis_csv",
                    leadership_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("leadership_kpis_csv", leadership_csv_path, None, False, _format_exception(exc))

        # 2c) Savings proof export (JSON + CSV) (best-effort; Pro+)
        savings_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "json",
            }
        )
        savings_url = _build_url(base_url, f"/api/v1/savings/proof?{savings_query}")
        savings_path = bundle_dir / "savings_proof.json"
        try:
            resp = await client.get(savings_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(savings_path, payload)
                record("savings_proof_json", savings_path, resp.status_code, True)
            else:
                record(
                    "savings_proof_json",
                    savings_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("savings_proof_json", savings_path, None, False, _format_exception(exc))

        savings_csv_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "csv",
            }
        )
        savings_csv_url = _build_url(
            base_url, f"/api/v1/savings/proof?{savings_csv_query}"
        )
        savings_csv_path = bundle_dir / "savings_proof.csv"
        try:
            resp = await client.get(savings_csv_url)
            if resp.is_success:
                _write_text(savings_csv_path, resp.text)
                record("savings_proof_csv", savings_csv_path, resp.status_code, True)
            else:
                record(
                    "savings_proof_csv",
                    savings_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("savings_proof_csv", savings_csv_path, None, False, _format_exception(exc))

        # 2d) Quarterly commercial proof report template (JSON + CSV) (best-effort; Pro+)
        quarterly_query = urlencode(
            {
                "period": "previous",
                "response_format": "json",
            }
        )
        quarterly_url = _build_url(
            base_url, f"/api/v1/leadership/reports/quarterly?{quarterly_query}"
        )
        quarterly_path = bundle_dir / "commercial_quarterly_report.json"
        try:
            resp = await client.get(quarterly_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(quarterly_path, payload)
                record(
                    "commercial_quarterly_report_json",
                    quarterly_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "commercial_quarterly_report_json",
                    quarterly_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "commercial_quarterly_report_json",
                quarterly_path,
                None,
                False,
                _format_exception(exc),
            )

        quarterly_csv_query = urlencode(
            {
                "period": "previous",
                "response_format": "csv",
            }
        )
        quarterly_csv_url = _build_url(
            base_url,
            f"/api/v1/leadership/reports/quarterly?{quarterly_csv_query}",
        )
        quarterly_csv_path = bundle_dir / "commercial_quarterly_report.csv"
        try:
            resp = await client.get(quarterly_csv_url)
            if resp.is_success:
                _write_text(quarterly_csv_path, resp.text)
                record(
                    "commercial_quarterly_report_csv",
                    quarterly_csv_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "commercial_quarterly_report_csv",
                    quarterly_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "commercial_quarterly_report_csv",
                quarterly_csv_path,
                None,
                False,
                _format_exception(exc),
            )

        # 3) Integration acceptance evidence (Slack/Jira/Workflow)
        evidence_url = _build_url(
            base_url, "/api/v1/settings/notifications/acceptance-evidence?limit=200"
        )
        evidence_path = bundle_dir / "integration_acceptance_evidence.json"
        try:
            resp = await client.get(evidence_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(evidence_path, payload)
                record(
                    "integration_acceptance_evidence_json",
                    evidence_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "integration_acceptance_evidence_json",
                    evidence_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "integration_acceptance_evidence_json",
                evidence_path,
                None,
                False,
                _format_exception(exc),
            )

        # 4) Job SLO snapshot (best-effort; admin-only, Pro+)
        slo_url = _build_url(base_url, "/api/v1/jobs/slo")
        slo_path = bundle_dir / "jobs_slo.json"
        try:
            resp = await client.get(slo_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(slo_path, payload)
                record("jobs_slo_json", slo_path, resp.status_code, True)
            else:
                record("jobs_slo_json", slo_path, resp.status_code, False, resp.text)
        except Exception as exc:
            record("jobs_slo_json", slo_path, None, False, _format_exception(exc))

        # 4b) Audit-grade Job SLO evidence snapshot (best-effort; admin-only)
        # This is computed server-side and persisted into audit logs for compliance packs.
        slo_window_hours = 24
        try:
            delta_days = (end_date - start_date).days
            slo_window_hours = max(24, min(24 * 30, int(delta_days) * 24))
        except Exception:
            slo_window_hours = 24 * 7

        slo_capture_url = _build_url(base_url, "/api/v1/audit/jobs/slo/evidence")
        slo_capture_path = bundle_dir / "job_slo_evidence_capture.json"
        try:
            resp = await client.post(
                slo_capture_url,
                json={
                    "window_hours": int(slo_window_hours),
                    "target_success_rate_percent": 95.0,
                },
            )
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(slo_capture_path, payload)
                record(
                    "job_slo_evidence_capture_json",
                    slo_capture_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "job_slo_evidence_capture_json",
                    slo_capture_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "job_slo_evidence_capture_json", slo_capture_path, None, False, _format_exception(exc)
            )

        slo_evidence_url = _build_url(
            base_url, "/api/v1/audit/jobs/slo/evidence?limit=200"
        )
        slo_evidence_path = bundle_dir / "job_slo_evidence.json"
        try:
            resp = await client.get(slo_evidence_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(slo_evidence_path, payload)
                record(
                    "job_slo_evidence_json", slo_evidence_path, resp.status_code, True
                )
            else:
                record(
                    "job_slo_evidence_json",
                    slo_evidence_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("job_slo_evidence_json", slo_evidence_path, None, False, _format_exception(exc))

        # 5) Profile snapshot (persona + tier)
        profile_url = _build_url(base_url, "/api/v1/settings/profile")
        profile_path = bundle_dir / "profile.json"
        try:
            resp = await client.get(profile_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(profile_path, payload)
                record("profile_json", profile_path, resp.status_code, True)
            else:
                record("profile_json", profile_path, resp.status_code, False, resp.text)
        except Exception as exc:
            record("profile_json", profile_path, None, False, _format_exception(exc))

        # 6) Month-end close package evidence (JSON + CSV) + restatements CSV
        close_params = {
            "start_date": close_start_date.isoformat(),
            "end_date": close_end_date.isoformat(),
            "enforce_finalized": str(bool(close_enforce_finalized)).lower(),
        }
        normalized_provider = str(close_provider or "all").strip().lower()
        if normalized_provider and normalized_provider != "all":
            close_params["provider"] = normalized_provider

        close_json_url = _build_url(
            base_url,
            f"/api/v1/costs/reconciliation/close-package?{urlencode({**close_params, 'response_format': 'json'})}",
        )
        close_json_path = bundle_dir / "close_package.json"
        try:
            resp = await client.get(close_json_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(close_json_path, payload)
                record("close_package_json", close_json_path, resp.status_code, True)
            else:
                record(
                    "close_package_json",
                    close_json_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("close_package_json", close_json_path, None, False, _format_exception(exc))

        close_csv_url = _build_url(
            base_url,
            f"/api/v1/costs/reconciliation/close-package?{urlencode({**close_params, 'response_format': 'csv'})}",
        )
        close_csv_path = bundle_dir / "close_package.csv"
        try:
            resp = await client.get(close_csv_url)
            if resp.is_success:
                _write_text(close_csv_path, resp.text)
                record("close_package_csv", close_csv_path, resp.status_code, True)
            else:
                record(
                    "close_package_csv",
                    close_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("close_package_csv", close_csv_path, None, False, _format_exception(exc))

        restatement_csv_url = _build_url(
            base_url,
            f"/api/v1/costs/reconciliation/restatements?{urlencode({**close_params, 'response_format': 'csv'})}",
        )
        restatement_csv_path = bundle_dir / "restatements.csv"
        try:
            resp = await client.get(restatement_csv_url)
            if resp.is_success:
                _write_text(restatement_csv_path, resp.text)
                record("restatements_csv", restatement_csv_path, resp.status_code, True)
            else:
                record(
                    "restatements_csv",
                    restatement_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("restatements_csv", restatement_csv_path, None, False, _format_exception(exc))

        # 7) Realized savings evidence (JSON + CSV) (best-effort; Pro+)
        realized_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "json",
                "limit": 500,
            }
        )
        realized_url = _build_url(
            base_url, f"/api/v1/savings/realized/events?{realized_query}"
        )
        realized_path = bundle_dir / "realized_savings.json"
        try:
            resp = await client.get(realized_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(realized_path, payload)
                record("realized_savings_json", realized_path, resp.status_code, True)
            else:
                record(
                    "realized_savings_json",
                    realized_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("realized_savings_json", realized_path, None, False, _format_exception(exc))

        realized_csv_query = urlencode(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "response_format": "csv",
                "limit": 500,
            }
        )
        realized_csv_url = _build_url(
            base_url, f"/api/v1/savings/realized/events?{realized_csv_query}"
        )
        realized_csv_path = bundle_dir / "realized_savings.csv"
        try:
            resp = await client.get(realized_csv_url)
            if resp.is_success:
                _write_text(realized_csv_path, resp.text)
                record(
                    "realized_savings_csv", realized_csv_path, resp.status_code, True
                )
            else:
                record(
                    "realized_savings_csv",
                    realized_csv_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("realized_savings_csv", realized_csv_path, None, False, _format_exception(exc))

        # 8) Performance evidence snapshots (best-effort; Pro+ admin)
        perf_url = _build_url(
            base_url, "/api/v1/audit/performance/load-test/evidence?limit=200"
        )
        perf_path = bundle_dir / "performance_load_test_evidence.json"
        try:
            resp = await client.get(perf_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(perf_path, payload)
                record(
                    "performance_load_test_evidence_json",
                    perf_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "performance_load_test_evidence_json",
                    perf_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "performance_load_test_evidence_json", perf_path, None, False, _format_exception(exc)
            )

        # 8b) Ingestion persistence benchmark evidence snapshots (best-effort; Pro+ admin)
        ingest_url = _build_url(
            base_url,
            "/api/v1/audit/performance/ingestion/persistence/evidence?limit=200",
        )
        ingest_path = bundle_dir / "ingestion_persistence_benchmark_evidence.json"
        try:
            resp = await client.get(ingest_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(ingest_path, payload)
                record(
                    "ingestion_persistence_benchmark_evidence_json",
                    ingest_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "ingestion_persistence_benchmark_evidence_json",
                    ingest_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "ingestion_persistence_benchmark_evidence_json",
                ingest_path,
                None,
                False,
                _format_exception(exc),
            )

        # 8c) Ingestion soak evidence snapshots (best-effort; Pro+ admin)
        soak_url = _build_url(
            base_url, "/api/v1/audit/performance/ingestion/soak/evidence?limit=200"
        )
        soak_path = bundle_dir / "ingestion_soak_evidence.json"
        try:
            resp = await client.get(soak_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(soak_path, payload)
                record(
                    "ingestion_soak_evidence_json", soak_path, resp.status_code, True
                )
            else:
                record(
                    "ingestion_soak_evidence_json",
                    soak_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("ingestion_soak_evidence_json", soak_path, None, False, _format_exception(exc))

        # 8d) Partitioning validation evidence snapshots (best-effort; Pro+ admin)
        partition_url = _build_url(
            base_url, "/api/v1/audit/performance/partitioning/evidence?limit=200"
        )
        partition_path = bundle_dir / "partitioning_evidence.json"
        try:
            resp = await client.get(partition_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(partition_path, payload)
                record(
                    "partitioning_evidence_json", partition_path, resp.status_code, True
                )
            else:
                record(
                    "partitioning_evidence_json",
                    partition_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("partitioning_evidence_json", partition_path, None, False, _format_exception(exc))

        # 9) Tenant isolation verification evidence snapshots (best-effort; Pro+ admin)
        isolation_url = _build_url(
            base_url, "/api/v1/audit/tenancy/isolation/evidence?limit=200"
        )
        isolation_path = bundle_dir / "tenant_isolation_evidence.json"
        try:
            resp = await client.get(isolation_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(isolation_path, payload)
                record(
                    "tenant_isolation_evidence_json",
                    isolation_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "tenant_isolation_evidence_json",
                    isolation_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "tenant_isolation_evidence_json", isolation_path, None, False, _format_exception(exc)
            )

        # 9b) Identity IdP smoke-test evidence snapshots (best-effort; Pro+ admin)
        identity_smoke_url = _build_url(
            base_url, "/api/v1/audit/identity/idp-smoke/evidence?limit=200"
        )
        identity_smoke_path = bundle_dir / "identity_smoke_evidence.json"
        try:
            resp = await client.get(identity_smoke_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(identity_smoke_path, payload)
                record(
                    "identity_smoke_evidence_json",
                    identity_smoke_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "identity_smoke_evidence_json",
                    identity_smoke_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "identity_smoke_evidence_json",
                identity_smoke_path,
                None,
                False,
                _format_exception(exc),
            )

        # 9c) SSO federation validation evidence snapshots (best-effort; Pro+ admin)
        sso_validation_url = _build_url(
            base_url, "/api/v1/audit/identity/sso-federation/evidence?limit=200"
        )
        sso_validation_path = bundle_dir / "sso_federation_validation_evidence.json"
        try:
            resp = await client.get(sso_validation_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(sso_validation_path, payload)
                record(
                    "sso_federation_validation_evidence_json",
                    sso_validation_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "sso_federation_validation_evidence_json",
                    sso_validation_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record(
                "sso_federation_validation_evidence_json",
                sso_validation_path,
                None,
                False,
                _format_exception(exc),
            )

        # 10) Carbon assurance evidence snapshots (best-effort; Pro+ admin)
        carbon_url = _build_url(
            base_url, "/api/v1/audit/carbon/assurance/evidence?limit=200"
        )
        carbon_path = bundle_dir / "carbon_assurance_evidence.json"
        try:
            resp = await client.get(carbon_url)
            if resp.is_success:
                payload = redact_secrets(resp.json())
                _write_json(carbon_path, payload)
                record(
                    "carbon_assurance_evidence_json",
                    carbon_path,
                    resp.status_code,
                    True,
                )
            else:
                record(
                    "carbon_assurance_evidence_json",
                    carbon_path,
                    resp.status_code,
                    False,
                    resp.text,
                )
        except Exception as exc:
            record("carbon_assurance_evidence_json", carbon_path, None, False, _format_exception(exc))

    manifest = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "close_window": {
            "start_date": close_start_date.isoformat(),
            "end_date": close_end_date.isoformat(),
            "provider": normalized_provider or "all",
            "enforce_finalized": bool(close_enforce_finalized),
        },
        "results": [r.__dict__ for r in results],
    }
    _write_json(bundle_dir / "manifest.json", manifest)
    return bundle_dir, results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture Valdrics acceptance evidence artifacts."
    )
    parser.add_argument(
        "--url", default=os.environ.get("VALDRICS_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--token", default=os.environ.get("VALDRICS_TOKEN"))
    parser.add_argument("--output-root", default="reports/acceptance")
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run capture against an in-process app + sqlite DB (no live environment required).",
    )
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--close-start-date", default=None)
    parser.add_argument("--close-end-date", default=None)
    parser.add_argument("--close-provider", default="all")
    parser.add_argument("--close-enforce-finalized", action="store_true")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP timeout for each capture request.",
    )
    args = parser.parse_args()

    transport: httpx.AsyncBaseTransport | None = None
    raw_url = str(args.url or "").strip()
    token = str(args.token or "").strip()
    if args.in_process:
        transport, token = asyncio.run(_bootstrap_in_process_app_and_token())
        base_url = "http://test"
    else:
        if not raw_url:
            # This happens when operators run: --url "$VALDRICS_API_URL" but the var is unset.
            # Fall back to the CLI default behavior instead of producing a full bundle of
            # "missing protocol" errors.
            fallback = (
                os.environ.get("VALDRICS_API_URL", "").strip() or "http://127.0.0.1:8000"
            )
            print(f"[acceptance] warning: empty --url; defaulting to {fallback}")
            raw_url = fallback
        base_url = _require_valid_base_url(raw_url)

    try:
        token = sanitize_bearer_token(token)
    except ValueError as exc:
        raise SystemExit(
            "Invalid token (VALDRICS_TOKEN/--token). "
            "Ensure it's a single JWT string. "
            f"Details: {exc}"
        ) from None

    if not token:
        raise SystemExit(
            "Missing token. Set VALDRICS_TOKEN or pass --token (or use --in-process)."
        )

    if args.start_date and args.end_date:
        start_date = _iso_date(args.start_date)
        end_date = _iso_date(args.end_date)
    else:
        start_date, end_date = _default_start_end()

    if args.close_start_date and args.close_end_date:
        close_start_date = _iso_date(args.close_start_date)
        close_end_date = _iso_date(args.close_end_date)
    else:
        close_start_date, close_end_date = _previous_full_month()

    if start_date > end_date:
        raise SystemExit("Invalid window: start_date must be <= end_date")
    if close_start_date > close_end_date:
        raise SystemExit(
            "Invalid close window: close_start_date must be <= close_end_date"
        )

    bundle_dir, results = asyncio.run(
        capture_acceptance_evidence(
            base_url=base_url,
            token=str(token).strip(),
            output_root=Path(args.output_root),
            start_date=start_date,
            end_date=end_date,
            close_start_date=close_start_date,
            close_end_date=close_end_date,
            close_provider=str(args.close_provider or "all"),
            close_enforce_finalized=bool(args.close_enforce_finalized),
            timeout_seconds=float(args.timeout_seconds),
            transport=transport,
        )
    )

    ok_count = sum(1 for r in results if r.ok)
    print(f"[acceptance] wrote bundle: {bundle_dir}")
    print(f"[acceptance] results: {ok_count}/{len(results)} ok")
    if ok_count == 0:
        print(
            "[acceptance] error: 0 captures succeeded. Check VALDRICS_API_URL/--url and VALDRICS_TOKEN."
        )
        print(f"[acceptance] details: {bundle_dir / 'manifest.json'}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
