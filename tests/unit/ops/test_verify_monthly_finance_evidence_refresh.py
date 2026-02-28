from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.verify_monthly_finance_evidence_refresh import (
    main,
    verify_monthly_refresh,
)


def _write(path: Path, *, captured_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"captured_at": captured_at}), encoding="utf-8")


AS_OF_UTC = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)


def test_verify_monthly_finance_refresh_accepts_fresh_artifacts(tmp_path: Path) -> None:
    finance_guardrails = tmp_path / "finance-guardrails.json"
    finance_telemetry = tmp_path / "finance-telemetry.json"
    pkg_fin = tmp_path / "pkg-fin.json"
    _write(finance_guardrails, captured_at="2026-02-27T10:00:00Z")
    _write(finance_telemetry, captured_at="2026-02-28T12:00:00Z")
    _write(pkg_fin, captured_at="2026-02-28T06:30:00Z")

    assert (
        verify_monthly_refresh(
            finance_guardrails_path=finance_guardrails,
            finance_telemetry_snapshot_path=finance_telemetry,
            pkg_fin_policy_decisions_path=pkg_fin,
            max_age_days=35.0,
            max_capture_spread_days=14.0,
            max_future_skew_hours=24.0,
            as_of=AS_OF_UTC,
        )
        == 0
    )


def test_verify_monthly_finance_refresh_rejects_stale_artifact(tmp_path: Path) -> None:
    finance_guardrails = tmp_path / "finance-guardrails.json"
    finance_telemetry = tmp_path / "finance-telemetry.json"
    pkg_fin = tmp_path / "pkg-fin.json"
    _write(finance_guardrails, captured_at="2026-01-01T00:00:00Z")
    _write(finance_telemetry, captured_at="2026-02-28T12:00:00Z")
    _write(pkg_fin, captured_at="2026-02-28T06:30:00Z")

    with pytest.raises(ValueError, match="evidence is stale"):
        verify_monthly_refresh(
            finance_guardrails_path=finance_guardrails,
            finance_telemetry_snapshot_path=finance_telemetry,
            pkg_fin_policy_decisions_path=pkg_fin,
            max_age_days=35.0,
            max_capture_spread_days=14.0,
            max_future_skew_hours=24.0,
            as_of=AS_OF_UTC,
        )


def test_verify_monthly_finance_refresh_rejects_wide_capture_spread(
    tmp_path: Path,
) -> None:
    finance_guardrails = tmp_path / "finance-guardrails.json"
    finance_telemetry = tmp_path / "finance-telemetry.json"
    pkg_fin = tmp_path / "pkg-fin.json"
    _write(finance_guardrails, captured_at="2026-02-01T00:00:00Z")
    _write(finance_telemetry, captured_at="2026-02-28T12:00:00Z")
    _write(pkg_fin, captured_at="2026-02-28T06:30:00Z")

    with pytest.raises(ValueError, match="capture spread is too wide"):
        verify_monthly_refresh(
            finance_guardrails_path=finance_guardrails,
            finance_telemetry_snapshot_path=finance_telemetry,
            pkg_fin_policy_decisions_path=pkg_fin,
            max_age_days=60.0,
            max_capture_spread_days=7.0,
            max_future_skew_hours=24.0,
            as_of=AS_OF_UTC,
        )


def test_verify_monthly_finance_refresh_rejects_future_skew_beyond_limit(
    tmp_path: Path,
) -> None:
    finance_guardrails = tmp_path / "finance-guardrails.json"
    finance_telemetry = tmp_path / "finance-telemetry.json"
    pkg_fin = tmp_path / "pkg-fin.json"
    _write(finance_guardrails, captured_at="2026-03-16T12:00:00Z")
    _write(finance_telemetry, captured_at="2026-03-16T12:00:00Z")
    _write(pkg_fin, captured_at="2026-03-16T12:00:00Z")

    with pytest.raises(ValueError, match="too far in the future"):
        verify_monthly_refresh(
            finance_guardrails_path=finance_guardrails,
            finance_telemetry_snapshot_path=finance_telemetry,
            pkg_fin_policy_decisions_path=pkg_fin,
            max_age_days=35.0,
            max_capture_spread_days=14.0,
            max_future_skew_hours=1.0,
            as_of=AS_OF_UTC,
        )


def test_main_accepts_valid_payloads(tmp_path: Path) -> None:
    finance_guardrails = tmp_path / "finance-guardrails.json"
    finance_telemetry = tmp_path / "finance-telemetry.json"
    pkg_fin = tmp_path / "pkg-fin.json"
    _write(finance_guardrails, captured_at="2026-02-27T10:00:00Z")
    _write(finance_telemetry, captured_at="2026-02-28T12:00:00Z")
    _write(pkg_fin, captured_at="2026-02-28T06:30:00Z")

    exit_code = main(
        [
            "--finance-guardrails-path",
            str(finance_guardrails),
            "--finance-telemetry-snapshot-path",
            str(finance_telemetry),
            "--pkg-fin-policy-decisions-path",
            str(pkg_fin),
            "--max-age-days",
            "35",
            "--max-capture-spread-days",
            "14",
            "--as-of",
            "2026-03-15T00:00:00Z",
        ]
    )
    assert exit_code == 0
