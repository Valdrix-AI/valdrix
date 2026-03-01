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


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return None


def _normalize_admin_sources(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        normalized = normalize_text(item)
        if normalized is not None:
            results.append(normalized)
    return results


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
        admin_role = normalize_text(
            row.get("admin_role") or row.get("org_role") or row.get("role")
        )
        mfa_enabled = _optional_bool(
            _first_present(
                row,
                (
                    "mfa_enabled",
                    "is_mfa_registered",
                    "two_factor_authentication",
                ),
            )
        )
        admin_sources = _normalize_admin_sources(row.get("admin_sources"))

        existing = records_by_id.get(identity)
        if existing is None:
            records_by_id[identity] = {
                "user_id": user_id or identity,
                "email": email,
                "full_name": full_name,
                "last_active_at": last_active,
                "is_admin": is_admin,
                "suspended": suspended,
                "admin_role": admin_role,
                "mfa_enabled": mfa_enabled,
                "admin_sources": admin_sources,
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
        if existing.get("admin_role") is None and admin_role is not None:
            existing["admin_role"] = admin_role
        if existing.get("mfa_enabled") is None and mfa_enabled is not None:
            existing["mfa_enabled"] = mfa_enabled
        merged_sources = {
            *(_normalize_admin_sources(existing.get("admin_sources"))),
            *admin_sources,
        }
        existing["admin_sources"] = sorted(merged_sources)

    results: list[dict[str, Any]] = []
    for identity in sorted(records_by_id):
        item = records_by_id[identity]
        last_active = _normalize_timestamp(item.get("last_active_at"))
        user_id = normalize_text(item.get("user_id")) or identity
        email = normalize_email(item.get("email"))
        full_name = normalize_text(item.get("full_name"))
        suspended = bool(item.get("suspended"))
        is_admin = bool(item.get("is_admin"))
        admin_role = normalize_text(item.get("admin_role"))
        mfa_enabled = _optional_bool(item.get("mfa_enabled"))
        admin_sources = _normalize_admin_sources(item.get("admin_sources"))

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
                    "admin_role": admin_role,
                    "mfa_enabled": mfa_enabled,
                    "admin_sources": admin_sources,
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
                    "admin_role": metadata_dict.get("admin_role"),
                    "mfa_enabled": _optional_bool(metadata_dict.get("mfa_enabled")),
                    "suspended": bool(metadata_dict.get("suspended")),
                },
            }
        )

    rows.sort(key=lambda item: str(item.get("resource_id") or ""))
    return rows
