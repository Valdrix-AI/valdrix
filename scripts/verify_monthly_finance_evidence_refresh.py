#!/usr/bin/env python3
"""Verify that finance evidence artifacts are refreshed on a monthly cadence."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceArtifact:
    label: str
    path: Path
    captured_at: datetime


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


def _parse_positive_float(value: Any, *, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if parsed <= 0.0:
        raise ValueError(f"{field} must be > 0")
    return parsed


def _load_artifact(*, path: Path, label: str) -> EvidenceArtifact:
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"{label} evidence artifact missing: {path}")
    raw = resolved.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} evidence is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} evidence payload must be a JSON object")
    captured_at = _parse_iso_utc(payload.get("captured_at"), field=f"{label}.captured_at")
    return EvidenceArtifact(label=label, path=resolved, captured_at=captured_at)


def verify_monthly_refresh(
    *,
    finance_guardrails_path: Path,
    finance_telemetry_snapshot_path: Path,
    pkg_fin_policy_decisions_path: Path,
    max_age_days: float,
    max_capture_spread_days: float,
    max_future_skew_hours: float,
    as_of: datetime | None = None,
) -> int:
    max_age_days = _parse_positive_float(max_age_days, field="max_age_days")
    max_capture_spread_days = _parse_positive_float(
        max_capture_spread_days,
        field="max_capture_spread_days",
    )
    if float(max_future_skew_hours) < 0.0:
        raise ValueError("max_future_skew_hours must be >= 0")
    now_utc = as_of.astimezone(timezone.utc) if as_of is not None else datetime.now(timezone.utc)

    artifacts = (
        _load_artifact(path=finance_guardrails_path, label="finance_guardrails"),
        _load_artifact(
            path=finance_telemetry_snapshot_path,
            label="finance_telemetry_snapshot",
        ),
        _load_artifact(
            path=pkg_fin_policy_decisions_path,
            label="pkg_fin_policy_decisions",
        ),
    )

    for artifact in artifacts:
        if artifact.captured_at > now_utc:
            future_skew_hours = (artifact.captured_at - now_utc).total_seconds() / 3600.0
            if future_skew_hours > float(max_future_skew_hours):
                raise ValueError(
                    f"{artifact.label}.captured_at is too far in the future "
                    f"({future_skew_hours:.2f}h > max {float(max_future_skew_hours):.2f}h): "
                    f"{artifact.captured_at.isoformat()}"
                )
        age_days = (now_utc - artifact.captured_at).total_seconds() / 86400.0
        if age_days > max_age_days:
            raise ValueError(
                f"{artifact.label} evidence is stale ({age_days:.2f} days > max {max_age_days:.2f}). "
                "Refresh monthly finance evidence artifacts before release."
            )

    oldest = min(artifact.captured_at for artifact in artifacts)
    newest = max(artifact.captured_at for artifact in artifacts)
    spread_days = (newest - oldest).total_seconds() / 86400.0
    if spread_days > max_capture_spread_days:
        raise ValueError(
            f"finance evidence capture spread is too wide ({spread_days:.2f} days > "
            f"max {max_capture_spread_days:.2f}); regenerate artifacts in the same monthly cycle."
        )

    print(
        "Monthly finance evidence refresh verified: "
        f"max_age_days={max_age_days:.2f}, "
        f"capture_spread_days={spread_days:.2f}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify monthly finance evidence refresh cadence for release gating.",
    )
    parser.add_argument(
        "--finance-guardrails-path",
        required=True,
        help="Path to finance guardrails evidence artifact JSON.",
    )
    parser.add_argument(
        "--finance-telemetry-snapshot-path",
        required=True,
        help="Path to finance telemetry snapshot evidence artifact JSON.",
    )
    parser.add_argument(
        "--pkg-fin-policy-decisions-path",
        required=True,
        help="Path to PKG/FIN policy decisions evidence artifact JSON.",
    )
    parser.add_argument(
        "--max-age-days",
        type=float,
        default=35.0,
        help="Maximum allowed age in days for each finance evidence artifact.",
    )
    parser.add_argument(
        "--max-capture-spread-days",
        type=float,
        default=14.0,
        help="Maximum allowed day spread between oldest/newest finance artifacts.",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Optional ISO-8601 UTC timestamp for deterministic validation runs.",
    )
    parser.add_argument(
        "--max-future-skew-hours",
        type=float,
        default=24.0,
        help="Maximum allowed future skew for captured_at timestamps.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    as_of = (
        _parse_iso_utc(args.as_of, field="as_of") if args.as_of is not None else None
    )
    return verify_monthly_refresh(
        finance_guardrails_path=Path(str(args.finance_guardrails_path)),
        finance_telemetry_snapshot_path=Path(str(args.finance_telemetry_snapshot_path)),
        pkg_fin_policy_decisions_path=Path(str(args.pkg_fin_policy_decisions_path)),
        max_age_days=float(args.max_age_days),
        max_capture_spread_days=float(args.max_capture_spread_days),
        max_future_skew_hours=float(args.max_future_skew_hours),
        as_of=as_of,
    )


if __name__ == "__main__":
    raise SystemExit(main())
