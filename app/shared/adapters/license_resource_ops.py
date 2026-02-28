from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.shared.adapters.license_feed_ops import (
    coerce_bool,
    normalize_email,
    normalize_text,
)

_DISCOVERY_RESOURCE_TYPE_ALIASES = {
    "all",
    "identity",
    "license",
    "license_seat",
    "license_seats",
    "licenses",
    "seat",
    "seats",
    "user",
    "users",
}

_USAGE_SERVICE_ALIASES = {
    "all",
    "identity",
    "license",
    "license_seat",
    "license_seats",
    "licenses",
    "seat",
    "seats",
    "user",
    "users",
}


def _normalize_resource_key(value: Any) -> str | None:
    normalized = normalize_text(value)
    if normalized is None:
        return None
    return normalized.lower()


def _normalize_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_currency(value: Any) -> str:
    normalized = normalize_text(value)
    if normalized is None:
        return "USD"
    upper = normalized.upper()
    return upper if upper else "USD"


def supports_license_discovery_resource_type(resource_type: str) -> bool:
    return _normalize_resource_key(resource_type) in _DISCOVERY_RESOURCE_TYPE_ALIASES


def supports_license_usage_service(service_name: str) -> bool:
    return _normalize_resource_key(service_name) in _USAGE_SERVICE_ALIASES


def build_discovered_license_resources(
    *,
    activity_rows: list[dict[str, Any]],
    vendor: str,
    resource_type: str,
    region: str | None,
) -> list[dict[str, Any]]:
    if not supports_license_discovery_resource_type(resource_type):
        return []

    normalized_region = normalize_text(region) or "global"
    records_by_id: dict[str, dict[str, Any]] = {}
    for row in activity_rows:
        if not isinstance(row, dict):
            continue
        user_id = normalize_text(row.get("user_id") or row.get("resource_id") or row.get("id"))
        email = normalize_email(row.get("email"))
        if email is None and user_id and "@" in user_id:
            email = user_id.lower()
        identity = user_id or email
        if identity is None:
            continue
        full_name = normalize_text(
            row.get("full_name") or row.get("display_name") or row.get("name")
        )
        last_active = _normalize_timestamp(row.get("last_active_at"))
        is_admin = coerce_bool(row.get("is_admin"))
        suspended = coerce_bool(row.get("suspended"))

        existing = records_by_id.get(identity)
        if existing is None:
            records_by_id[identity] = {
                "user_id": user_id or identity,
                "email": email,
                "full_name": full_name,
                "last_active_at": last_active,
                "is_admin": is_admin,
                "suspended": suspended,
            }
            continue

        if existing.get("email") is None and email is not None:
            existing["email"] = email
        if existing.get("full_name") is None and full_name is not None:
            existing["full_name"] = full_name
        if last_active is not None:
            existing_last = _normalize_timestamp(existing.get("last_active_at"))
            if existing_last is None or last_active > existing_last:
                existing["last_active_at"] = last_active
        existing["is_admin"] = bool(existing.get("is_admin") or is_admin)
        existing["suspended"] = bool(existing.get("suspended") or suspended)

    results: list[dict[str, Any]] = []
    for identity in sorted(records_by_id):
        item = records_by_id[identity]
        last_active = _normalize_timestamp(item.get("last_active_at"))
        user_id = normalize_text(item.get("user_id")) or identity
        email = normalize_email(item.get("email"))
        full_name = normalize_text(item.get("full_name"))
        suspended = bool(item.get("suspended"))
        is_admin = bool(item.get("is_admin"))

        results.append(
            {
                "id": identity,
                "name": full_name or email or user_id,
                "type": "license_seat",
                "provider": "license",
                "region": normalized_region,
                "status": "suspended" if suspended else "active",
                "metadata": {
                    "resource_type": "license_seat",
                    "vendor": vendor,
                    "user_id": user_id,
                    "email": email,
                    "full_name": full_name,
                    "is_admin": is_admin,
                    "suspended": suspended,
                    "last_active_at": (
                        last_active.isoformat() if last_active is not None else None
                    ),
                },
            }
        )
    return results


def build_license_usage_rows(
    *,
    activity_rows: list[dict[str, Any]],
    vendor: str,
    service_name: str,
    resource_id: str | None,
    default_seat_price_usd: float,
    currency: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not supports_license_usage_service(service_name):
        return []

    normalized_default_price = max(default_seat_price_usd, 0.0)
    normalized_resource_id = _normalize_resource_key(resource_id)
    resolved_now = now or datetime.now(timezone.utc)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=timezone.utc)

    discovered = build_discovered_license_resources(
        activity_rows=activity_rows,
        vendor=vendor,
        resource_type="license",
        region="global",
    )
    rows: list[dict[str, Any]] = []
    for resource in discovered:
        if not isinstance(resource, dict):
            continue
        current_resource_id = _normalize_resource_key(resource.get("id"))
        if current_resource_id is None:
            continue
        if (
            normalized_resource_id is not None
            and current_resource_id != normalized_resource_id
        ):
            continue

        metadata = resource.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        last_active_iso = metadata_dict.get("last_active_at")
        timestamp = resolved_now
        if isinstance(last_active_iso, str) and last_active_iso.strip():
            iso_candidate = last_active_iso.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(iso_candidate)
                timestamp = (
                    parsed
                    if parsed.tzinfo is not None
                    else parsed.replace(tzinfo=timezone.utc)
                )
            except ValueError:
                timestamp = resolved_now

        rows.append(
            {
                "provider": "license",
                "service": "license",
                "region": "global",
                "usage_type": "seat_activity",
                "resource_id": resource["id"],
                "usage_amount": 1.0,
                "usage_unit": "seat",
                "cost_usd": normalized_default_price,
                "amount_raw": None,
                "currency": _normalize_currency(currency),
                "timestamp": timestamp,
                "source_adapter": "license_activity",
                "tags": {
                    "vendor": vendor,
                    "email": metadata_dict.get("email"),
                    "user_id": metadata_dict.get("user_id"),
                    "is_admin": bool(metadata_dict.get("is_admin")),
                    "suspended": bool(metadata_dict.get("suspended")),
                },
            }
        )

    rows.sort(key=lambda item: str(item.get("resource_id") or ""))
    return rows
