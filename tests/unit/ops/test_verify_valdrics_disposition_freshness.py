from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.verify_valdrics_disposition_freshness import (
    DEFAULT_REQUIRED_FINDING_IDS,
    main,
    verify_disposition_register,
)


AS_OF_UTC = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_payload() -> dict[str, object]:
    dispositions: list[dict[str, object]] = []
    for finding_id in DEFAULT_REQUIRED_FINDING_IDS:
        item: dict[str, object] = {
            "finding_id": finding_id,
            "status": "documented_exception",
            "owner": "platform-owner@valdrics.io",
            "review_by": "2026-03-31",
            "rationale": f"{finding_id} disposition rationale recorded for release gate.",
            "exit_criteria": f"{finding_id} closure criteria tracked in remediation backlog.",
        }
        if finding_id in {"VAL-ADAPT-001", "VAL-ADAPT-002+"}:
            item["status"] = "planned_refactor"
            item["backlog_ref"] = "VAL-ADAPT-002+"
        dispositions.append(item)

    return {
        "captured_at": "2026-02-28T15:20:00Z",
        "source_audit_path": "/tmp/VALDRX_CODEBASE_AUDIT_2026-02-28.md.resolved",
        "dispositions": dispositions,
    }


def test_verify_valdrics_disposition_freshness_accepts_valid_payload(
    tmp_path: Path,
) -> None:
    path = tmp_path / "valdrics-disposition.json"
    _write(path, _valid_payload())

    assert (
        verify_disposition_register(
            register_path=path,
            max_artifact_age_days=45.0,
            max_review_window_days=120.0,
            as_of=AS_OF_UTC,
        )
        == 0
    )


def test_verify_valdrics_disposition_freshness_rejects_overdue_review(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["dispositions"][0]["review_by"] = "2026-03-01"
    path = tmp_path / "valdrics-disposition.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="review_by is overdue"):
        verify_disposition_register(
            register_path=path,
            max_artifact_age_days=45.0,
            max_review_window_days=120.0,
            as_of=AS_OF_UTC,
        )


def test_verify_valdrics_disposition_freshness_rejects_placeholder_owner(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["dispositions"][0]["owner"] = "owner@example.com"
    path = tmp_path / "valdrics-disposition.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="must not contain placeholder tokens"):
        verify_disposition_register(
            register_path=path,
            max_artifact_age_days=45.0,
            max_review_window_days=120.0,
            as_of=AS_OF_UTC,
        )


def test_verify_valdrics_disposition_freshness_rejects_missing_required_finding(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["dispositions"] = payload["dispositions"][:-1]
    path = tmp_path / "valdrics-disposition.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="missing required finding IDs"):
        verify_disposition_register(
            register_path=path,
            max_artifact_age_days=45.0,
            max_review_window_days=120.0,
            as_of=AS_OF_UTC,
        )


def test_main_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "valdrics-disposition.json"
    _write(path, _valid_payload())
    assert (
        main(
            [
                "--register-path",
                str(path),
                "--max-artifact-age-days",
                "45",
                "--max-review-window-days",
                "120",
                "--as-of",
                "2026-03-15T00:00:00Z",
            ]
        )
        == 0
    )
