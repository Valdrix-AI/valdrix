from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.verify_enforcement_stress_evidence import main, verify_evidence


BASE_VERIFY_KWARGS = {
    "expected_profile": "enforcement",
    "min_rounds": 3,
    "min_duration_seconds": 30,
    "min_concurrent_users": 10,
    "required_database_engine": "postgresql",
    "max_p95_seconds": 2.0,
    "max_error_rate_percent": 1.0,
    "min_throughput_rps": 0.5,
}


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _verify(path: Path, **overrides: object) -> int:
    kwargs = dict(BASE_VERIFY_KWARGS)
    kwargs.update(overrides)
    return verify_evidence(evidence_path=path, **kwargs)


def _valid_payload() -> dict[str, object]:
    run_results = [
        {
            "total_requests": 400,
            "successful_requests": 399,
            "failed_requests": 1,
            "throughput_rps": 3.5,
            "p95_response_time": 1.3,
            "p99_response_time": 1.8,
        },
        {
            "total_requests": 400,
            "successful_requests": 399,
            "failed_requests": 1,
            "throughput_rps": 4.8,
            "p95_response_time": 1.42,
            "p99_response_time": 1.95,
        },
        {
            "total_requests": 400,
            "successful_requests": 399,
            "failed_requests": 1,
            "throughput_rps": 6.1,
            "p95_response_time": 1.2,
            "p99_response_time": 1.7,
        },
    ]
    return {
        "profile": "enforcement",
        "runner": "scripts/load_test_api.py",
        "captured_at": "2026-02-27T05:30:00Z",
        "runtime": {"database_engine": "postgresql"},
        "endpoints": [
            "/health/live",
            "/api/v1/enforcement/policies",
            "/api/v1/enforcement/budgets",
            "/api/v1/enforcement/credits",
            "/api/v1/enforcement/ledger?limit=50",
            "/api/v1/enforcement/exports/parity?limit=50",
        ],
        "duration_seconds": 30,
        "concurrent_users": 10,
        "rounds": 3,
        "runs": [
            {
                "run_index": 1,
                "captured_at": "2026-02-27T05:30:01Z",
                "results": dict(run_results[0]),
            },
            {
                "run_index": 2,
                "captured_at": "2026-02-27T05:30:02Z",
                "results": dict(run_results[1]),
            },
            {
                "run_index": 3,
                "captured_at": "2026-02-27T05:30:03Z",
                "results": dict(run_results[2]),
            },
        ],
        "preflight": {"enabled": True, "passed": True, "failures": []},
        "results": {
            "total_requests": 1200,
            "successful_requests": 1197,  # 399 * 3
            "failed_requests": 3,  # 1 * 3
            "p95_response_time": 1.42,
            "p99_response_time": 1.95,
            "throughput_rps": 4.8,
        },
        "min_throughput_rps": 3.5,
        "thresholds": {
            "max_p95_seconds": 2.0,
            "max_error_rate_percent": 1.0,
            "min_throughput_rps": 0.5,
        },
        "evaluation": {
            "rounds": [
                {"round": 1, "meets_targets": True},
                {"round": 2, "meets_targets": True},
                {"round": 3, "meets_targets": True},
            ],
            "overall_meets_targets": True,
            "worst_p95_seconds": 1.42,
            "min_throughput_rps": 3.5,
        },
        "meets_targets": True,
    }


def test_verify_evidence_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    _write(path, _valid_payload())
    assert _verify(path) == 0


def test_verify_evidence_rejects_profile_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["profile"] = "ops"
    path = tmp_path / "evidence.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="Unexpected profile"):
        _verify(path)


def test_verify_evidence_rejects_failed_preflight(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["preflight"] = {"enabled": True, "passed": False}
    path = tmp_path / "evidence.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="preflight.passed"):
        _verify(path)


def test_verify_evidence_rejects_high_p95(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["results"]["p95_response_time"] = 4.2
    path = tmp_path / "evidence.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="p95_response_time"):
        _verify(path)


def test_verify_evidence_rejects_high_error_rate(tmp_path: Path) -> None:
    payload = _valid_payload()
    for run in payload["runs"]:
        run_results = run["results"]
        run_results["total_requests"] = 100
        run_results["failed_requests"] = 5
        run_results["successful_requests"] = 95
    payload["results"]["failed_requests"] = 15
    payload["results"]["total_requests"] = 300
    payload["results"]["successful_requests"] = 285
    path = tmp_path / "evidence.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="error rate"):
        _verify(path)


def test_verify_evidence_rejects_missing_enforcement_endpoint(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["endpoints"] = ["/health/live", "/api/v1/costs"]
    path = tmp_path / "evidence.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="enforcement API endpoints"):
        _verify(path)


def test_verify_evidence_rejects_underpowered_or_incomplete_profile(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["duration_seconds"] = 20
    path = tmp_path / "duration-too-low.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="duration_seconds must be >="):
        _verify(path)

    payload = _valid_payload()
    payload["concurrent_users"] = 7
    path = tmp_path / "users-too-low.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="concurrent_users must be >="):
        _verify(path)

    payload = _valid_payload()
    payload["endpoints"] = [
        "/health/live",
        "/api/v1/enforcement/policies",
        "/api/v1/enforcement/ledger?limit=50",
    ]
    path = tmp_path / "missing-required-endpoint.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required enforcement endpoints"):
        _verify(path)


def test_verify_evidence_rejects_runner_or_timestamp_contract_violations(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["runner"] = "scripts/unknown.py"
    path = tmp_path / "runner-invalid.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="runner must equal"):
        _verify(path)

    payload = _valid_payload()
    payload["captured_at"] = "2026-02-27T05:30:00"
    path = tmp_path / "captured-at-invalid.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="timezone information"):
        _verify(path)


def test_verify_evidence_rejects_runtime_database_backend_mismatch(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["runtime"] = {"database_engine": "sqlite"}
    path = tmp_path / "database-engine-mismatch.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="does not match required verifier backend"):
        _verify(path)

    payload = _valid_payload()
    payload["runtime"] = {}
    path = tmp_path / "database-engine-missing.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="runtime.database_engine must be"):
        _verify(path)


def test_verify_evidence_rejects_round_alignment_or_success_count_drift(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["runs"] = [{"round": 1}]
    path = tmp_path / "runs-short.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="runs must be an array"):
        _verify(path)

    payload = _valid_payload()
    payload["results"]["successful_requests"] = 1100
    path = tmp_path / "success-drift.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="successful_requests must equal"):
        _verify(path)


def test_verify_evidence_rejects_run_index_or_aggregate_tampering(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["runs"][1]["run_index"] = 7
    path = tmp_path / "run-index-invalid.json"
    _write(path, payload)
    with pytest.raises(ValueError, match=r"run_index must equal"):
        _verify(path)

    payload = _valid_payload()
    payload["results"]["p95_response_time"] = 0.9
    path = tmp_path / "aggregate-tamper.json"
    _write(path, payload)
    with pytest.raises(ValueError, match=r"p95_response_time must equal max"):
        _verify(path)


def test_verify_evidence_rejects_evaluation_consistency_violations(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["evaluation"]["rounds"] = [
        {"round": 1, "meets_targets": True},
        {"round": 2, "meets_targets": False},
        {"round": 3, "meets_targets": True},
    ]
    payload["evaluation"]["overall_meets_targets"] = True
    path = tmp_path / "overall-mismatch.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="must match all"):
        _verify(path)

    payload = _valid_payload()
    payload["meets_targets"] = False
    path = tmp_path / "meets-targets-false.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="meets_targets must be true"):
        _verify(path)


def test_verify_evidence_rejects_threshold_or_evaluation_aggregate_mismatches(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["thresholds"]["max_p95_seconds"] = 3.0
    path = tmp_path / "threshold-p95-mismatch.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="thresholds.max_p95_seconds must match"):
        _verify(path)

    payload = _valid_payload()
    payload["evaluation"]["worst_p95_seconds"] = 1.0
    path = tmp_path / "evaluation-p95-mismatch.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="evaluation.worst_p95_seconds must equal"):
        _verify(path)

    payload = _valid_payload()
    payload["evaluation"]["rounds"] = [{"round": 1, "meets_targets": True}]
    path = tmp_path / "evaluation-round-count-mismatch.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="exactly `rounds` entries"):
        _verify(path)


def test_verify_evidence_rejects_stale_artifact_when_freshness_bound_enabled(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    payload["captured_at"] = "2024-01-01T00:00:00Z"
    path = tmp_path / "stale.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="captured_at is too old"):
        _verify(path, max_artifact_age_hours=24.0)


def test_verify_evidence_rejects_invalid_freshness_bound(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    _write(path, _valid_payload())
    with pytest.raises(ValueError, match="max_artifact_age_hours must be > 0"):
        _verify(path, max_artifact_age_hours=0.0)


def test_main_succeeds_for_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    _write(path, _valid_payload())
    exit_code = main(["--evidence-path", str(path)])
    assert exit_code == 0
