from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.verify_enforcement_stress_evidence import main, verify_evidence


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_payload() -> dict[str, object]:
    return {
        "profile": "enforcement",
        "endpoints": [
            "/health/live",
            "/api/v1/enforcement/policies",
            "/api/v1/enforcement/ledger?limit=50",
        ],
        "rounds": 3,
        "preflight": {"enabled": True, "passed": True},
        "results": {
            "total_requests": 1200,
            "failed_requests": 3,
            "p95_response_time": 1.42,
        },
        "min_throughput_rps": 3.5,
        "evaluation": {"overall_meets_targets": True},
    }


def test_verify_evidence_accepts_valid_payload(tmp_path: Path) -> None:
    payload = _valid_payload()
    path = tmp_path / "evidence.json"
    _write(path, payload)

    exit_code = verify_evidence(
        evidence_path=path,
        expected_profile="enforcement",
        min_rounds=3,
        max_p95_seconds=2.0,
        max_error_rate_percent=1.0,
        min_throughput_rps=0.5,
    )

    assert exit_code == 0


def test_verify_evidence_rejects_profile_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["profile"] = "ops"
    path = tmp_path / "evidence.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="Unexpected profile"):
        verify_evidence(
            evidence_path=path,
            expected_profile="enforcement",
            min_rounds=3,
            max_p95_seconds=2.0,
            max_error_rate_percent=1.0,
            min_throughput_rps=0.5,
        )


def test_verify_evidence_rejects_failed_preflight(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["preflight"] = {"enabled": True, "passed": False}
    path = tmp_path / "evidence.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="preflight.passed"):
        verify_evidence(
            evidence_path=path,
            expected_profile="enforcement",
            min_rounds=3,
            max_p95_seconds=2.0,
            max_error_rate_percent=1.0,
            min_throughput_rps=0.5,
        )


def test_verify_evidence_rejects_high_p95(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["results"]["p95_response_time"] = 4.2
    path = tmp_path / "evidence.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="p95_response_time"):
        verify_evidence(
            evidence_path=path,
            expected_profile="enforcement",
            min_rounds=3,
            max_p95_seconds=2.0,
            max_error_rate_percent=1.0,
            min_throughput_rps=0.5,
        )


def test_verify_evidence_rejects_high_error_rate(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["results"]["failed_requests"] = 25
    payload["results"]["total_requests"] = 100
    path = tmp_path / "evidence.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="error rate"):
        verify_evidence(
            evidence_path=path,
            expected_profile="enforcement",
            min_rounds=3,
            max_p95_seconds=2.0,
            max_error_rate_percent=1.0,
            min_throughput_rps=0.5,
        )


def test_verify_evidence_rejects_missing_enforcement_endpoint(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["endpoints"] = ["/health/live", "/api/v1/costs"]
    path = tmp_path / "evidence.json"
    _write(path, payload)

    with pytest.raises(ValueError, match="enforcement API endpoints"):
        verify_evidence(
            evidence_path=path,
            expected_profile="enforcement",
            min_rounds=3,
            max_p95_seconds=2.0,
            max_error_rate_percent=1.0,
            min_throughput_rps=0.5,
        )


def test_main_succeeds_for_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    _write(path, _valid_payload())

    exit_code = main(["--evidence-path", str(path)])
    assert exit_code == 0
