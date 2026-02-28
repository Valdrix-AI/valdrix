#!/usr/bin/env python3
"""Verify Valdrix audit disposition evidence freshness and ownership."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_DISPOSITION_STATUSES = {
    "accepted_risk",
    "planned_refactor",
    "documented_exception",
}
DEFAULT_REQUIRED_FINDING_IDS: tuple[str, ...] = (
    "VAL-ADAPT-001",
    "VAL-DB-002",
    "VAL-DB-003",
    "VAL-DB-004",
    "VAL-API-001",
    "VAL-API-002",
    "VAL-API-004",
    "VAL-ADAPT-002+",
)
FINDING_ID_RE = re.compile(r"^VAL-[A-Z]+-[0-9]+(?:\+)?$")
PLACEHOLDER_TOKEN_RE = re.compile(
    r"(?:\b(?:todo|tbd|placeholder|replace(?:_|-)?me|changeme)\b|example\.com|\.example\b|yyyy)",
    flags=re.IGNORECASE,
)


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
        raise ValueError(f"{field} must be a non-empty ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO date (YYYY-MM-DD)") from exc


def _parse_positive_float(value: Any, *, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if parsed <= 0.0:
        raise ValueError(f"{field} must be > 0")
    return parsed


def _parse_non_empty_str(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} must be a non-empty string")
    if PLACEHOLDER_TOKEN_RE.search(normalized):
        raise ValueError(f"{field} must not contain placeholder tokens")
    return normalized


def _load_payload(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Valdrix disposition register not found: {path}")
    raw = resolved.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Valdrix disposition register is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Valdrix disposition register payload must be a JSON object")
    return payload


def verify_disposition_register(
    *,
    register_path: Path,
    max_artifact_age_days: float,
    max_review_window_days: float,
    required_finding_ids: tuple[str, ...] = DEFAULT_REQUIRED_FINDING_IDS,
    as_of: datetime | None = None,
) -> int:
    max_artifact_age_days = _parse_positive_float(
        max_artifact_age_days, field="max_artifact_age_days"
    )
    max_review_window_days = _parse_positive_float(
        max_review_window_days, field="max_review_window_days"
    )

    payload = _load_payload(register_path)
    now_utc = as_of.astimezone(timezone.utc) if as_of is not None else datetime.now(timezone.utc)
    today_utc = now_utc.date()

    captured_at = _parse_iso_utc(payload.get("captured_at"), field="captured_at")
    artifact_age_days = (now_utc - captured_at).total_seconds() / 86400.0
    if artifact_age_days > max_artifact_age_days:
        raise ValueError(
            f"Disposition register is stale ({artifact_age_days:.2f} days > max "
            f"{max_artifact_age_days:.2f})."
        )

    source_audit_path = _parse_non_empty_str(
        payload.get("source_audit_path"),
        field="source_audit_path",
    )
    _ = source_audit_path

    dispositions = payload.get("dispositions")
    if not isinstance(dispositions, list) or not dispositions:
        raise ValueError("dispositions must be a non-empty array")

    seen_ids: set[str] = set()
    latest_review_by = today_utc
    for idx, item in enumerate(dispositions):
        if not isinstance(item, dict):
            raise ValueError(f"dispositions[{idx}] must be an object")
        finding_id = _parse_non_empty_str(
            item.get("finding_id"),
            field=f"dispositions[{idx}].finding_id",
        )
        if not FINDING_ID_RE.match(finding_id):
            raise ValueError(
                f"dispositions[{idx}].finding_id has invalid format: {finding_id}"
            )
        if finding_id in seen_ids:
            raise ValueError(f"duplicate disposition finding_id: {finding_id}")
        seen_ids.add(finding_id)

        status = _parse_non_empty_str(
            item.get("status"),
            field=f"dispositions[{idx}].status",
        )
        if status not in ALLOWED_DISPOSITION_STATUSES:
            raise ValueError(
                f"dispositions[{idx}].status must be one of "
                f"{sorted(ALLOWED_DISPOSITION_STATUSES)}"
            )

        _parse_non_empty_str(
            item.get("owner"),
            field=f"dispositions[{idx}].owner",
        )
        _parse_non_empty_str(
            item.get("rationale"),
            field=f"dispositions[{idx}].rationale",
        )
        _parse_non_empty_str(
            item.get("exit_criteria"),
            field=f"dispositions[{idx}].exit_criteria",
        )
        if status == "planned_refactor":
            _parse_non_empty_str(
                item.get("backlog_ref"),
                field=f"dispositions[{idx}].backlog_ref",
            )

        review_by = _parse_iso_date(
            item.get("review_by"),
            field=f"dispositions[{idx}].review_by",
        )
        latest_review_by = max(latest_review_by, review_by)
        if review_by < today_utc:
            raise ValueError(
                f"dispositions[{idx}].review_by is overdue: {review_by.isoformat()}"
            )
        review_window_days = float((review_by - today_utc).days)
        if review_window_days > max_review_window_days:
            raise ValueError(
                f"dispositions[{idx}].review_by exceeds max review window "
                f"({review_window_days:.0f} days > {max_review_window_days:.0f})"
            )

    missing_required = set(required_finding_ids) - seen_ids
    if missing_required:
        raise ValueError(
            "disposition register missing required finding IDs: "
            + ", ".join(sorted(missing_required))
        )

    print(
        "Valdrix disposition freshness verified: "
        f"findings={len(seen_ids)} "
        f"captured_at={captured_at.isoformat()} "
        f"latest_review_by={latest_review_by.isoformat()}"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Valdrix disposition evidence freshness, ownership, and review windows."
        ),
    )
    parser.add_argument(
        "--register-path",
        required=True,
        help="Path to Valdrix disposition register JSON artifact.",
    )
    parser.add_argument(
        "--max-artifact-age-days",
        type=float,
        default=45.0,
        help="Maximum allowed age for captured_at in days.",
    )
    parser.add_argument(
        "--max-review-window-days",
        type=float,
        default=120.0,
        help="Maximum allowed days into the future for review_by deadlines.",
    )
    parser.add_argument(
        "--required-finding-id",
        action="append",
        default=[],
        help=(
            "Required finding ID; may be repeated. "
            "Defaults to the built-in Valdrix disposition set when omitted."
        ),
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Optional ISO-8601 UTC timestamp for deterministic validation runs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    as_of = _parse_iso_utc(args.as_of, field="as_of") if args.as_of else None
    required_ids = tuple(args.required_finding_id) or DEFAULT_REQUIRED_FINDING_IDS
    return verify_disposition_register(
        register_path=Path(str(args.register_path)),
        max_artifact_age_days=float(args.max_artifact_age_days),
        max_review_window_days=float(args.max_review_window_days),
        required_finding_ids=required_ids,
        as_of=as_of,
    )


if __name__ == "__main__":
    raise SystemExit(main())
