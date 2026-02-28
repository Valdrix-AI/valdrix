from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_email(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized or "@" not in normalized:
        return None
    return normalized


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return False


def validate_manual_feed(
    feed: Any,
    *,
    is_number_fn: Callable[[Any], bool],
) -> str | None:
    """
    Validate manual/csv license feed structure.

    Returns:
    - `None` when valid.
    - Human-readable error message when invalid.
    """
    if not isinstance(feed, list) or not feed:
        return "License feed must contain at least one record for manual/csv verification."

    for idx, entry in enumerate(feed):
        if not isinstance(entry, dict):
            return f"License feed entry #{idx + 1} must be a JSON object."
        has_timestamp = entry.get("timestamp") or entry.get("date")
        if not has_timestamp:
            return f"License feed entry #{idx + 1} is missing timestamp/date."
        amount = entry.get("cost_usd", entry.get("amount_usd"))
        if not is_number_fn(amount):
            return (
                f"License feed entry #{idx + 1} must include numeric cost_usd or amount_usd."
            )
    return None


def iter_manual_cost_rows(
    *,
    feed: Any,
    start_date: datetime,
    end_date: datetime,
    parse_timestamp_fn: Callable[[Any], datetime],
    as_float_fn: Callable[..., float],
    is_number_fn: Callable[[Any], bool],
) -> Iterable[dict[str, Any]]:
    if not isinstance(feed, list):
        return ()

    rows: list[dict[str, Any]] = []
    for entry in feed:
        timestamp = parse_timestamp_fn(entry.get("timestamp") or entry.get("date"))
        if timestamp < start_date or timestamp > end_date:
            continue
        resource_id_raw = entry.get("resource_id") or entry.get("id")
        resource_id = (
            str(resource_id_raw).strip() if resource_id_raw not in (None, "") else None
        )
        usage_amount_raw = entry.get("usage_amount")
        usage_amount = (
            as_float_fn(usage_amount_raw, default=0.0)
            if is_number_fn(usage_amount_raw)
            else None
        )
        usage_unit_raw = entry.get("usage_unit")
        usage_unit = (
            str(usage_unit_raw).strip() if usage_unit_raw not in (None, "") else None
        )
        rows.append(
            {
                "provider": "license",
                "service": str(entry.get("service") or entry.get("vendor") or "License"),
                "region": "global",
                "usage_type": str(entry.get("usage_type") or "seat_license"),
                "resource_id": resource_id,
                "usage_amount": usage_amount,
                "usage_unit": usage_unit,
                "cost_usd": float(entry.get("cost_usd") or entry.get("amount_usd") or 0.0),
                "amount_raw": entry.get("amount_raw"),
                "currency": str(entry.get("currency") or "USD"),
                "timestamp": timestamp,
                "source_adapter": "license_feed",
                "tags": entry.get("tags") if isinstance(entry.get("tags"), dict) else {},
            }
        )

    return rows


def list_manual_feed_activity(
    *,
    feed: Any,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    """
    Build user activity records from manual/csv license feeds.

    Expected optional keys per feed row:
    user_id/email/resource_id, last_active_at/last_login_at/timestamp, is_admin/role,
    suspended/inactive/status.
    """
    if not isinstance(feed, list):
        return []

    consolidated: dict[str, dict[str, Any]] = {}
    for entry in feed:
        if not isinstance(entry, dict):
            continue

        user_id = normalize_text(
            entry.get("user_id")
            or entry.get("principal_id")
            or entry.get("resource_id")
            or entry.get("id")
        )
        email = normalize_email(entry.get("email"))
        if email is None and user_id and "@" in user_id:
            email = user_id.lower()

        identity = user_id or email
        if not identity:
            continue

        last_active_at = None
        for candidate in (
            entry.get("last_active_at"),
            entry.get("last_login_at"),
            entry.get("last_login"),
            entry.get("last_activity_at"),
            entry.get("last_seen_at"),
            entry.get("timestamp"),
            entry.get("date"),
        ):
            if candidate in (None, ""):
                continue
            try:
                last_active_at = parse_timestamp_fn(candidate)
            except (TypeError, ValueError):
                continue
            break

        role = str(entry.get("role") or "").strip().lower()
        is_admin = coerce_bool(entry.get("is_admin")) or role in {
            "admin",
            "owner",
            "super_admin",
            "system administrator",
        }
        status = str(entry.get("status") or "").strip().lower()
        suspended = (
            coerce_bool(entry.get("suspended"))
            or coerce_bool(entry.get("inactive"))
            or status in {"inactive", "suspended", "disabled", "deactivated"}
        )

        full_name = normalize_text(
            entry.get("full_name") or entry.get("display_name") or entry.get("name")
        )

        current = consolidated.get(identity)
        if current is None:
            consolidated[identity] = {
                "user_id": user_id or email or identity,
                "email": email,
                "full_name": full_name,
                "last_active_at": last_active_at,
                "is_admin": is_admin,
                "suspended": suspended,
            }
            continue

        if not current.get("email") and email:
            current["email"] = email
        if not current.get("full_name") and full_name:
            current["full_name"] = full_name
        if last_active_at is not None:
            existing_last = current.get("last_active_at")
            if existing_last is None or last_active_at > existing_last:
                current["last_active_at"] = last_active_at

        current["is_admin"] = bool(current.get("is_admin") or is_admin)
        current["suspended"] = bool(current.get("suspended") or suspended)

    return list(consolidated.values())
