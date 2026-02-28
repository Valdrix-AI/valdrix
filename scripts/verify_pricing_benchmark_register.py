#!/usr/bin/env python3
"""Validate pricing benchmark evidence register for PKG-020 cadence controls."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ALLOWED_SOURCE_CLASSES = {
    "vendor_pricing_page",
    "industry_benchmark_report",
    "standards_guidance",
    "analyst_report",
}
DEFAULT_REQUIRED_SOURCE_CLASSES = (
    "vendor_pricing_page",
    "industry_benchmark_report",
    "standards_guidance",
)
DEFAULT_MINIMUM_SOURCE_COUNT = 5
DEFAULT_MINIMUM_CONFIDENCE_SCORE = 0.7


def _parse_iso_utc(value: Any, *, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty ISO-8601 datetime")
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _parse_float(
    value: Any,
    *,
    field: str,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{field} must be <= {max_value}")
    return parsed


def _parse_int(value: Any, *, field: str, min_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be integer-like") from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(f"{field} must be >= {min_value}")
    return parsed


def _parse_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be boolean")


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Pricing benchmark register file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Pricing benchmark register JSON is invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Pricing benchmark register payload must be a JSON object")
    return payload


def _validate_https_url(value: Any, *, field: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty URL")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be a valid https URL")
    return raw


def verify_register(
    *,
    register_path: Path,
    max_source_age_days: float | None = None,
) -> int:
    payload = _load_payload(register_path)
    captured_at = _parse_iso_utc(payload.get("captured_at"), field="captured_at")

    refresh_policy = payload.get("refresh_policy")
    if not isinstance(refresh_policy, dict):
        raise ValueError("refresh_policy must be an object")

    register_max_source_age_days = _parse_float(
        refresh_policy.get("max_source_age_days"),
        field="refresh_policy.max_source_age_days",
        min_value=1.0,
    )
    effective_max_source_age_days = (
        _parse_float(
            max_source_age_days,
            field="max_source_age_days",
            min_value=1.0,
        )
        if max_source_age_days is not None
        else register_max_source_age_days
    )

    required_classes_raw = refresh_policy.get(
        "required_source_classes", list(DEFAULT_REQUIRED_SOURCE_CLASSES)
    )
    if not isinstance(required_classes_raw, list) or not required_classes_raw:
        raise ValueError("refresh_policy.required_source_classes must be a non-empty array")
    required_classes: set[str] = set()
    for idx, source_class in enumerate(required_classes_raw):
        normalized = str(source_class or "").strip()
        if normalized not in ALLOWED_SOURCE_CLASSES:
            raise ValueError(
                "refresh_policy.required_source_classes "
                f"contains unsupported class at index {idx}: {source_class}"
            )
        required_classes.add(normalized)

    thresholds = payload.get("thresholds", {})
    if not isinstance(thresholds, dict):
        raise ValueError("thresholds must be an object")
    minimum_source_count = _parse_int(
        thresholds.get("minimum_source_count", DEFAULT_MINIMUM_SOURCE_COUNT),
        field="thresholds.minimum_source_count",
        min_value=1,
    )
    minimum_confidence_score = _parse_float(
        thresholds.get("minimum_confidence_score", DEFAULT_MINIMUM_CONFIDENCE_SCORE),
        field="thresholds.minimum_confidence_score",
        min_value=0.0,
        max_value=1.0,
    )

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a non-empty array")

    class_counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    stale_source_ids: list[str] = []
    low_confidence_ids: list[str] = []
    oldest_age_days = 0.0
    now = datetime.now(timezone.utc)
    for idx, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"sources[{idx}] must be an object")
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            raise ValueError(f"sources[{idx}].id must be a non-empty string")
        if source_id in seen_ids:
            raise ValueError(f"sources[{idx}].id must be unique: {source_id}")
        seen_ids.add(source_id)
        _ = _validate_https_url(source.get("url"), field=f"sources[{idx}].url")
        source_class = str(source.get("source_class") or "").strip()
        if source_class not in ALLOWED_SOURCE_CLASSES:
            raise ValueError(
                f"sources[{idx}].source_class must be one of "
                f"{sorted(ALLOWED_SOURCE_CLASSES)}"
            )
        class_counts[source_class] = class_counts.get(source_class, 0) + 1
        crawled_at = _parse_iso_utc(
            source.get("crawled_at"), field=f"sources[{idx}].crawled_at"
        )
        if crawled_at > captured_at:
            raise ValueError(
                f"sources[{idx}].crawled_at must be <= captured_at"
            )
        age_days_now = (now - crawled_at).total_seconds() / 86400.0
        age_days_at_capture = (captured_at - crawled_at).total_seconds() / 86400.0
        oldest_age_days = max(oldest_age_days, age_days_at_capture)
        if age_days_now > effective_max_source_age_days:
            stale_source_ids.append(source_id)
        confidence_score = _parse_float(
            source.get("confidence_score"),
            field=f"sources[{idx}].confidence_score",
            min_value=0.0,
            max_value=1.0,
        )
        if confidence_score < minimum_confidence_score:
            low_confidence_ids.append(source_id)

    required_classes_present = required_classes.issubset(set(class_counts))
    minimum_sources_met = len(sources) >= minimum_source_count
    register_fresh = len(stale_source_ids) == 0

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")
    summary_total_sources = _parse_int(
        summary.get("total_sources"),
        field="summary.total_sources",
        min_value=1,
    )
    if summary_total_sources != len(sources):
        raise ValueError(
            "summary.total_sources must match computed source count"
        )
    summary_class_counts = summary.get("class_counts")
    if not isinstance(summary_class_counts, dict):
        raise ValueError("summary.class_counts must be an object")
    for source_class, count in class_counts.items():
        summary_count = _parse_int(
            summary_class_counts.get(source_class),
            field=f"summary.class_counts.{source_class}",
            min_value=0,
        )
        if summary_count != count:
            raise ValueError(
                "summary.class_counts mismatch for "
                f"{source_class}: expected {count}, got {summary_count}"
            )
    summary_oldest_age_days = _parse_float(
        summary.get("oldest_source_age_days"),
        field="summary.oldest_source_age_days",
        min_value=0.0,
    )
    if round(summary_oldest_age_days, 2) != round(oldest_age_days, 2):
        raise ValueError(
            "summary.oldest_source_age_days must match computed oldest source age"
        )

    gate_results = payload.get("gate_results")
    if not isinstance(gate_results, dict):
        raise ValueError("gate_results must be an object")
    expected_gate_results = {
        "pkg_gate_020_register_fresh": register_fresh,
        "pkg_gate_020_required_classes_present": required_classes_present,
        "pkg_gate_020_minimum_sources_met": minimum_sources_met,
    }
    for key, expected in expected_gate_results.items():
        actual = _parse_bool(gate_results.get(key), field=f"gate_results.{key}")
        if actual != expected:
            raise ValueError(
                f"gate_results.{key} mismatch: expected {expected}, got {actual}"
            )

    if not required_classes_present:
        missing = sorted(required_classes - set(class_counts))
        raise ValueError(f"missing required source classes: {missing}")
    if not minimum_sources_met:
        raise ValueError(
            f"sources count must be >= {minimum_source_count}"
        )
    if stale_source_ids:
        raise ValueError(
            "stale sources exceed max age: "
            f"{', '.join(sorted(stale_source_ids))}"
        )
    if low_confidence_ids:
        raise ValueError(
            "sources below minimum confidence threshold: "
            f"{', '.join(sorted(low_confidence_ids))}"
        )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate pricing benchmark evidence register for PKG-020 controls."
    )
    parser.add_argument(
        "--register-path",
        required=True,
        help="Path to pricing benchmark evidence register JSON file.",
    )
    parser.add_argument(
        "--max-source-age-days",
        type=float,
        default=None,
        help=(
            "Maximum allowed age for source crawls in days. "
            "If omitted, refresh_policy.max_source_age_days is used."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_register(
        register_path=Path(args.register_path),
        max_source_age_days=args.max_source_age_days,
    )


if __name__ == "__main__":
    raise SystemExit(main())
