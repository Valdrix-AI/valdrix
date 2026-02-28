from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.shared.adapters.feed_utils import as_float, is_number, parse_timestamp

_DEFAULT_LOOKBACK_DAYS = 30
_MAX_LOOKBACK_DAYS = 365
_SERVICE_KEYS = ("service", "sku_description", "product", "usage_type")
_RESOURCE_KEYS = ("resource_id", "ResourceId", "resource.name", "id", "resource")
_TAG_RESOURCE_KEYS = (
    "resource_id",
    "ResourceId",
    "id",
    "resource.name",
    "instance_id",
    "vm_id",
)


def resource_usage_lookback_window(
    *, lookback_days: int = _DEFAULT_LOOKBACK_DAYS, now: datetime | None = None
) -> tuple[datetime, datetime]:
    end_date = now or datetime.now(timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    safe_lookback = max(1, min(int(lookback_days), _MAX_LOOKBACK_DAYS))
    return end_date - timedelta(days=safe_lookback), end_date


def project_cost_rows_to_resource_usage(
    *,
    cost_rows: list[dict[str, Any]],
    service_name: str,
    resource_id: str | None,
    default_provider: str,
    default_source_adapter: str,
) -> list[dict[str, Any]]:
    target_service = _normalize_optional_str(service_name)
    if target_service is None:
        return []

    target_service_lc = target_service.lower()
    target_resource = _normalize_optional_str(resource_id)
    target_resource_lc = target_resource.lower() if target_resource else None

    usage_rows: list[dict[str, Any]] = []
    for row in cost_rows:
        if not isinstance(row, dict):
            continue

        resolved_service = _resolve_service(row) or target_service
        if not _service_matches(target_service_lc, resolved_service):
            continue

        resolved_resource_id = _resolve_resource_id(row)
        if target_resource_lc and (
            resolved_resource_id is None
            or resolved_resource_id.lower() != target_resource_lc
        ):
            continue

        usage_amount = _coerce_optional_float(row.get("usage_amount"))
        usage_unit = _normalize_optional_str(row.get("usage_unit"))
        if usage_amount is not None and usage_unit is None:
            usage_unit = "unit"

        cost_usd = _coerce_optional_float(row.get("cost_usd"))
        if cost_usd is None:
            cost_usd = _coerce_optional_float(row.get("amount_usd"))
        if cost_usd is None:
            cost_usd = _coerce_optional_float(row.get("amount_raw"))
        if cost_usd is None:
            cost_usd = 0.0

        amount_raw = _coerce_optional_float(row.get("amount_raw"))
        if amount_raw is None:
            amount_raw = cost_usd

        usage_rows.append(
            {
                "provider": _normalize_optional_str(row.get("provider"))
                or default_provider,
                "service": resolved_service,
                "resource_id": resolved_resource_id,
                "usage_type": _normalize_optional_str(row.get("usage_type"))
                or "resource_usage",
                "usage_amount": usage_amount,
                "usage_unit": usage_unit,
                "cost_usd": cost_usd,
                "amount_raw": amount_raw,
                "currency": (
                    _normalize_optional_str(row.get("currency")) or "USD"
                ).upper(),
                "region": _normalize_optional_str(row.get("region")) or "global",
                "timestamp": parse_timestamp(row.get("timestamp")),
                "source_adapter": _normalize_optional_str(row.get("source_adapter"))
                or default_source_adapter,
                "tags": row.get("tags") if isinstance(row.get("tags"), dict) else {},
            }
        )

    usage_rows.sort(
        key=lambda item: (
            item["timestamp"],
            str(item.get("resource_id") or ""),
            str(item["service"]),
        )
    )
    return usage_rows


def _resolve_service(row: dict[str, Any]) -> str | None:
    for key in _SERVICE_KEYS:
        value = _normalize_optional_str(row.get(key))
        if value is not None:
            return value
    return None


def _resolve_resource_id(row: dict[str, Any]) -> str | None:
    for key in _RESOURCE_KEYS:
        value = _normalize_optional_str(row.get(key))
        if value is not None:
            return value

    tags = row.get("tags")
    if isinstance(tags, dict):
        for key in _TAG_RESOURCE_KEYS:
            value = _normalize_optional_str(tags.get(key))
            if value is not None:
                return value
    return None


def _service_matches(target_service_lc: str, candidate: str) -> bool:
    candidate_lc = candidate.strip().lower()
    return target_service_lc in candidate_lc


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if not is_number(value):
        return None
    return as_float(value, default=0.0)


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None

