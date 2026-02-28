from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.verify_pricing_benchmark_register import main, verify_register


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _base_payload(*, captured_at: datetime | None = None) -> dict[str, object]:
    captured = (captured_at or datetime.now(timezone.utc)).replace(microsecond=0)
    crawled = (captured - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    captured_raw = captured.isoformat().replace("+00:00", "Z")
    return {
        "captured_at": captured_raw,
        "refresh_policy": {
            "max_source_age_days": 120,
            "required_source_classes": [
                "vendor_pricing_page",
                "industry_benchmark_report",
                "standards_guidance",
            ],
            "refresh_cadence": "quarterly",
        },
        "thresholds": {
            "minimum_source_count": 5,
            "minimum_confidence_score": 0.7,
        },
        "sources": [
            {
                "id": "a",
                "url": "https://example.com/a",
                "source_class": "vendor_pricing_page",
                "crawled_at": crawled,
                "confidence_score": 0.9,
            },
            {
                "id": "b",
                "url": "https://example.com/b",
                "source_class": "industry_benchmark_report",
                "crawled_at": crawled,
                "confidence_score": 0.85,
            },
            {
                "id": "c",
                "url": "https://example.com/c",
                "source_class": "standards_guidance",
                "crawled_at": crawled,
                "confidence_score": 0.95,
            },
            {
                "id": "d",
                "url": "https://example.com/d",
                "source_class": "standards_guidance",
                "crawled_at": crawled,
                "confidence_score": 0.92,
            },
            {
                "id": "e",
                "url": "https://example.com/e",
                "source_class": "vendor_pricing_page",
                "crawled_at": crawled,
                "confidence_score": 0.88,
            },
        ],
        "summary": {
            "total_sources": 5,
            "class_counts": {
                "vendor_pricing_page": 2,
                "industry_benchmark_report": 1,
                "standards_guidance": 2,
            },
            "oldest_source_age_days": 0.04,
        },
        "gate_results": {
            "pkg_gate_020_register_fresh": True,
            "pkg_gate_020_required_classes_present": True,
            "pkg_gate_020_minimum_sources_met": True,
        },
    }


def test_verify_pricing_benchmark_register_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "pricing-register.json"
    _write(path, _base_payload())
    assert verify_register(register_path=path) == 0


def test_verify_pricing_benchmark_register_rejects_gate_mismatch(tmp_path: Path) -> None:
    payload = _base_payload()
    payload["gate_results"]["pkg_gate_020_minimum_sources_met"] = False
    path = tmp_path / "pricing-register.json"
    _write(path, payload)
    with pytest.raises(
        ValueError,
        match="gate_results.pkg_gate_020_minimum_sources_met mismatch",
    ):
        verify_register(register_path=path)


def test_verify_pricing_benchmark_register_rejects_missing_required_class(
    tmp_path: Path,
) -> None:
    payload = _base_payload()
    payload["refresh_policy"]["required_source_classes"] = [
        "vendor_pricing_page",
        "industry_benchmark_report",
        "standards_guidance",
        "analyst_report",
    ]
    payload["gate_results"]["pkg_gate_020_required_classes_present"] = False
    path = tmp_path / "pricing-register.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="missing required source classes"):
        verify_register(register_path=path)


def test_verify_pricing_benchmark_register_rejects_stale_sources(tmp_path: Path) -> None:
    captured = datetime.now(timezone.utc).replace(microsecond=0)
    stale = (captured - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    payload = _base_payload(captured_at=captured)
    payload["refresh_policy"]["max_source_age_days"] = 5
    payload["sources"][0]["crawled_at"] = stale
    payload["summary"]["oldest_source_age_days"] = 10.0
    payload["gate_results"]["pkg_gate_020_register_fresh"] = False
    path = tmp_path / "pricing-register.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="stale sources exceed max age"):
        verify_register(register_path=path)


def test_verify_pricing_benchmark_register_rejects_summary_drift(tmp_path: Path) -> None:
    payload = _base_payload()
    payload["summary"]["total_sources"] = 99
    path = tmp_path / "pricing-register.json"
    _write(path, payload)
    with pytest.raises(ValueError, match="summary.total_sources must match"):
        verify_register(register_path=path)


def test_main_accepts_valid_payload(tmp_path: Path) -> None:
    path = tmp_path / "pricing-register.json"
    _write(path, _base_payload())
    assert main(["--register-path", str(path)]) == 0
