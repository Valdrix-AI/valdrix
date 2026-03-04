from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping, TYPE_CHECKING, cast

from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
)
from app.shared.core.config import get_settings

if TYPE_CHECKING:
    from app.models.enforcement import EnforcementSource
    from app.modules.enforcement.domain.service_models import GateInput


_POLICY_DOCUMENT_SCHEMA_VERSION_DEFAULT = "valdrics.enforcement.policy.v1"
_POLICY_DOCUMENT_SHA256_EMPTY = "0" * 64
_SUPPORTED_REVIEWER_ROLES = ("owner", "admin", "member")
_DEFAULT_ALLOWED_REVIEWER_ROLES = ("owner", "admin")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _as_utc(parsed)


def _iso_or_empty(value: datetime | None) -> str:
    if value is None:
        return ""
    return _as_utc(value).isoformat()


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places))


def _normalize_environment(value: str) -> str:
    env = str(value or "").strip().lower()
    if env in {"prod", "production", "live"}:
        return "prod"
    if env in {"nonprod", "non-prod", "dev", "test", "stage", "staging"}:
        return "nonprod"
    return env or "nonprod"


def _is_production_environment(value: str) -> bool:
    return _normalize_environment(value) == "prod"


def _normalize_role_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _normalize_string_list(
    values: Iterable[Any] | None,
    *,
    normalizer: Callable[[str], str] | None = None,
) -> list[str]:
    normalized: list[str] = []
    if values is None:
        return normalized

    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        key = normalizer(value) if normalizer is not None else value.lower()
        if key not in normalized:
            normalized.append(key)
    return normalized


def _normalize_allowed_reviewer_roles(values: Iterable[Any] | None) -> list[str]:
    roles: list[str] = []
    if values is None:
        return list(_DEFAULT_ALLOWED_REVIEWER_ROLES)

    for raw in values:
        role = _normalize_role_value(raw)
        if role not in _SUPPORTED_REVIEWER_ROLES:
            continue
        if role not in roles:
            roles.append(role)
    if not roles:
        return list(_DEFAULT_ALLOWED_REVIEWER_ROLES)
    return roles


def _default_required_permission_for_environment(environment: str) -> str:
    if _is_production_environment(environment):
        return APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    return APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported type for canonical json: {type(value)}")


def _payload_sha256(payload: Mapping[str, Any] | None) -> str:
    serialized = json.dumps(
        dict(payload or {}),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _sanitize_csv_cell(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).replace("\r", " ").replace("\n", " ")
    if normalized[:1] in {"=", "+", "-", "@"}:
        return "'" + normalized
    return normalized


def _computed_context_snapshot(
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    computed_context_raw = (
        response_payload.get("computed_context")
        if isinstance(response_payload, Mapping)
        else None
    )
    computed_context = (
        cast(Mapping[str, Any], computed_context_raw)
        if isinstance(computed_context_raw, Mapping)
        else {}
    )

    def _ctx_str(key: str) -> str:
        return str(computed_context.get(key) or "").strip()

    def _ctx_int(key: str) -> int:
        raw = computed_context.get(key)
        if raw is None:
            return 0
        if isinstance(raw, bool):
            return int(raw)
        if not isinstance(raw, (int, float, Decimal, str)):
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    return {
        "context_version": _ctx_str("context_version"),
        "generated_at": _ctx_str("generated_at"),
        "month_start": _ctx_str("month_start"),
        "month_end": _ctx_str("month_end"),
        "month_elapsed_days": _ctx_int("month_elapsed_days"),
        "month_total_days": _ctx_int("month_total_days"),
        "observed_cost_days": _ctx_int("observed_cost_days"),
        "latest_cost_date": _ctx_str("latest_cost_date"),
        "data_source_mode": _ctx_str("data_source_mode"),
    }


def _stable_fingerprint(source: EnforcementSource, gate_input: GateInput) -> str:
    canonical = {
        "source": source.value,
        "project_id": gate_input.project_id,
        "environment": _normalize_environment(gate_input.environment),
        "action": gate_input.action,
        "resource_reference": gate_input.resource_reference,
        "estimated_monthly_delta_usd": str(
            _quantize(gate_input.estimated_monthly_delta_usd, "0.0001")
        ),
        "estimated_hourly_delta_usd": str(
            _quantize(gate_input.estimated_hourly_delta_usd, "0.000001")
        ),
        "metadata": gate_input.metadata,
    }
    serialized = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _unique_reason_codes(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        key = str(value or "").strip().lower()
        if not key:
            continue
        if key not in ordered:
            ordered.append(key)
    return ordered


def _normalize_policy_document_schema_version(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return _POLICY_DOCUMENT_SCHEMA_VERSION_DEFAULT
    return normalized[:64]


def _normalize_policy_document_sha256(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64:
        return _POLICY_DOCUMENT_SHA256_EMPTY
    if any(ch not in "0123456789abcdef" for ch in normalized):
        return _POLICY_DOCUMENT_SHA256_EMPTY
    return normalized


def _gate_lock_timeout_seconds() -> float:
    raw = getattr(get_settings(), "ENFORCEMENT_GATE_TIMEOUT_SECONDS", 2.0)
    try:
        gate_timeout = float(raw)
    except (TypeError, ValueError):
        gate_timeout = 2.0
    gate_timeout = max(0.05, min(gate_timeout, 30.0))
    return max(0.05, min(gate_timeout * 0.8, 5.0))
