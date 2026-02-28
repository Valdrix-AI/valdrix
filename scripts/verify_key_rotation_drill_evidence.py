"""Validate staged key-rotation drill evidence for enforcement release gates."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

DEFAULT_DRILL_PATH = "docs/ops/key-rotation-drill-2026-02-27.md"
DEFAULT_MAX_DRILL_AGE_DAYS = 120.0

REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
    "drill_id",
    "environment",
    "owner",
    "approver",
    "post_drill_status",
)

REQUIRED_BOOL_FIELDS: tuple[str, ...] = (
    "pre_rotation_tokens_accepted",
    "post_rotation_new_tokens_accepted",
    "post_rotation_old_tokens_rejected",
    "fallback_verification_passed",
    "rollback_validation_passed",
    "replay_protection_intact",
    "alert_pipeline_verified",
)

_FIELD_RE = re.compile(r"^- ([a-z0-9_]+):\s*(.+)\s*$")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def _parse_iso_date(value: Any, *, field: str) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{field} must be a non-empty ISO date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def _load_raw(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Drill evidence file not found: {path}")
    return path.read_text(encoding="utf-8")


def _extract_kv_fields(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        match = _FIELD_RE.match(line.strip())
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key in values:
            raise ValueError(f"Duplicate field in drill evidence: {key}")
        values[key] = value
    return values


def _parse_bool(value: str, *, field: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    raise ValueError(f"{field} must be boolean-like (true/false)")


def verify_key_rotation_drill_evidence(
    *,
    drill_path: Path,
    max_drill_age_days: float,
) -> int:
    raw = _load_raw(drill_path)
    fields = _extract_kv_fields(raw)

    for field in REQUIRED_TEXT_FIELDS:
        if not fields.get(field, "").strip():
            raise ValueError(f"Missing required text field: {field}")

    if fields["post_drill_status"].strip().upper() != "PASS":
        raise ValueError("post_drill_status must be PASS")

    owner = fields["owner"].strip()
    approver = fields["approver"].strip()
    if owner == approver:
        raise ValueError("owner and approver must be different principals")

    for field in REQUIRED_BOOL_FIELDS:
        value = _parse_bool(fields.get(field, ""), field=field)
        if value is not True:
            raise ValueError(f"{field} must be true")

    executed_at_utc = _parse_iso_utc(fields.get("executed_at_utc"), field="executed_at_utc")
    next_drill_due_on = _parse_iso_date(fields.get("next_drill_due_on"), field="next_drill_due_on")

    now_utc = _utcnow()
    if executed_at_utc > (now_utc + timedelta(minutes=5)):
        raise ValueError("executed_at_utc cannot be in the future")

    max_age = float(max_drill_age_days)
    if max_age <= 0:
        raise ValueError("max_drill_age_days must be > 0")
    drill_age_days = (now_utc - executed_at_utc).total_seconds() / 86400.0
    if drill_age_days > max_age:
        raise ValueError(
            "key-rotation drill evidence is too old "
            f"({drill_age_days:.2f} days > max {max_age:.2f} days)"
        )

    if next_drill_due_on < executed_at_utc.date():
        raise ValueError("next_drill_due_on cannot be earlier than drill date")
    if next_drill_due_on < now_utc.date():
        raise ValueError("next_drill_due_on cannot be in the past")

    print(
        "Key rotation drill evidence verified: "
        f"drill_id={fields['drill_id']} "
        f"executed_at={executed_at_utc.isoformat()} "
        f"next_due={next_drill_due_on.isoformat()} "
        f"age_days={drill_age_days:.2f}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate staged key-rotation drill evidence contract."
    )
    parser.add_argument(
        "--drill-path",
        default=DEFAULT_DRILL_PATH,
        help="Path to key rotation drill evidence markdown.",
    )
    parser.add_argument(
        "--max-drill-age-days",
        type=float,
        default=DEFAULT_MAX_DRILL_AGE_DAYS,
        help=f"Maximum allowed drill age in days (default: {DEFAULT_MAX_DRILL_AGE_DAYS}).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return verify_key_rotation_drill_evidence(
        drill_path=Path(args.drill_path),
        max_drill_age_days=float(args.max_drill_age_days),
    )


if __name__ == "__main__":
    raise SystemExit(main())
