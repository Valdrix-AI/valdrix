from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import scripts.verify_key_rotation_drill_evidence as drill_verifier


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _valid_doc(*, executed_at_utc: str = "2026-02-27T08:10:00Z") -> str:
    return f"""# Evidence

- drill_id: KRD-2026-02-27-ENF-001
- executed_at_utc: {executed_at_utc}
- environment: staging
- owner: security-oncall
- approver: platform-oncall
- next_drill_due_on: 2026-05-28
- pre_rotation_tokens_accepted: true
- post_rotation_new_tokens_accepted: true
- post_rotation_old_tokens_rejected: true
- fallback_verification_passed: true
- rollback_validation_passed: true
- replay_protection_intact: true
- alert_pipeline_verified: true
- post_drill_status: PASS
"""


def test_verify_key_rotation_drill_evidence_accepts_valid_doc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc())
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    exit_code = drill_verifier.verify_key_rotation_drill_evidence(
        drill_path=path,
        max_drill_age_days=120.0,
    )

    assert exit_code == 0


def test_verify_key_rotation_drill_evidence_rejects_non_pass_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc().replace("post_drill_status: PASS", "post_drill_status: FAIL"))
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="post_drill_status must be PASS"):
        drill_verifier.verify_key_rotation_drill_evidence(
            drill_path=path,
            max_drill_age_days=120.0,
        )


def test_verify_key_rotation_drill_evidence_rejects_same_owner_and_approver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    payload = _valid_doc().replace("approver: platform-oncall", "approver: security-oncall")
    _write(path, payload)
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="owner and approver must be different"):
        drill_verifier.verify_key_rotation_drill_evidence(
            drill_path=path,
            max_drill_age_days=120.0,
        )


def test_verify_key_rotation_drill_evidence_rejects_stale_drill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc(executed_at_utc="2025-01-01T00:00:00Z"))
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="too old"):
        drill_verifier.verify_key_rotation_drill_evidence(
            drill_path=path,
            max_drill_age_days=120.0,
        )


def test_verify_key_rotation_drill_evidence_rejects_invalid_max_age(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc())
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="max_drill_age_days must be > 0"):
        drill_verifier.verify_key_rotation_drill_evidence(
            drill_path=path,
            max_drill_age_days=0.0,
        )


def test_verify_key_rotation_drill_evidence_rejects_future_execution_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc(executed_at_utc="2026-02-27T23:59:59Z"))
    monkeypatch.setattr(
        drill_verifier,
        "_utcnow",
        lambda: datetime(2026, 2, 27, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="cannot be in the future"):
        drill_verifier.verify_key_rotation_drill_evidence(
            drill_path=path,
            max_drill_age_days=120.0,
        )


def test_main_succeeds_for_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "drill.md"
    _write(path, _valid_doc())

    exit_code = drill_verifier.main(
        [
            "--drill-path",
            str(path),
            "--max-drill-age-days",
            "99999",
        ]
    )

    assert exit_code == 0
