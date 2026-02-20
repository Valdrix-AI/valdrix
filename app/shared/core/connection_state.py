from __future__ import annotations

from typing import Any

from app.shared.core.config import get_settings
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection

_PRODUCTION_MARKERS = ("prod", "production", "critical", "pci", "hipaa")
_NON_PRODUCTION_MARKERS = (
    "dev",
    "development",
    "staging",
    "stage",
    "sandbox",
    "test",
    "qa",
)
_PRODUCTION_ENV_VALUES = {"prod", "production", "live"}
_NON_PRODUCTION_ENV_VALUES = {
    "dev",
    "development",
    "staging",
    "stage",
    "sandbox",
    "test",
    "qa",
}
_CRITICALITY_VALUES = {"low", "medium", "high", "critical"}


def _default_aws_region() -> str:
    raw_default = str(get_settings().AWS_DEFAULT_REGION or "").strip()
    return raw_default or "us-east-1"


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _coerce_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_criticality(value: Any) -> str | None:
    text = _coerce_text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in _CRITICALITY_VALUES:
        return normalized
    return None


def _extract_profile_value(connection: Any, key: str) -> Any:
    direct = getattr(connection, key, None)
    if direct is not None:
        return direct

    raw_config = getattr(connection, "connector_config", None)
    if isinstance(raw_config, dict):
        return raw_config.get(key)

    return None


def infer_is_production_from_name(name: Any) -> bool | None:
    text = str(name or "").strip().lower()
    if not text:
        return None
    if any(marker in text for marker in _NON_PRODUCTION_MARKERS):
        return False
    if any(marker in text for marker in _PRODUCTION_MARKERS):
        return True
    return None


def resolve_connection_profile(connection: Any) -> dict[str, Any]:
    """
    Resolve production/criticality profile for a connection.

    Precedence:
    1. Explicit `is_production` on the model or connector config.
    2. Explicit `environment` on the model or connector config.
    3. Inference from connection name.
    """
    explicit_is_production = _coerce_bool(
        _extract_profile_value(connection, "is_production")
    )
    if explicit_is_production is not None:
        source = "explicit_is_production"
    else:
        source = "unknown"

    if explicit_is_production is None:
        environment = _coerce_text(_extract_profile_value(connection, "environment"))
        env_normalized = environment.lower() if environment else None
        if env_normalized in _PRODUCTION_ENV_VALUES:
            explicit_is_production = True
            source = "explicit_environment"
        elif env_normalized in _NON_PRODUCTION_ENV_VALUES:
            explicit_is_production = False
            source = "explicit_environment"

    if explicit_is_production is None:
        explicit_is_production = infer_is_production_from_name(
            getattr(connection, "name", None)
        )
        if explicit_is_production is not None:
            source = "name_inference"

    criticality = _coerce_criticality(_extract_profile_value(connection, "criticality"))

    return {
        "is_production": explicit_is_production,
        "criticality": criticality,
        "source": source,
    }


def is_connection_active(connection: Any) -> bool:
    """
    Provider-agnostic active-state check for connection models.

    - AWS-style models expose `status` and are active only when `status == "active"`.
    - Other providers use `is_active` and default to True when absent.
    """
    status_value = getattr(connection, "status", None)
    if isinstance(status_value, str):
        return status_value.strip().lower() == "active"
    if isinstance(status_value, bool):
        return status_value

    active_value = getattr(connection, "is_active", None)
    if isinstance(active_value, bool):
        return active_value
    if active_value is None:
        return True
    if type(active_value).__name__ == "InstrumentedAttribute":
        return True

    # Preserve deterministic behavior under mocked objects in tests where
    # arbitrary attributes may resolve to mock instances.
    return True


def resolve_connection_region(connection: Any) -> str:
    """
    Provider-aware connection region defaulting for scheduler payloads.

    - AWS defaults to configured `AWS_DEFAULT_REGION` when region is missing.
    - Other providers default to `global`.
    """
    provider = normalize_provider(resolve_provider_from_connection(connection))
    raw_region_value = getattr(connection, "region", None)
    if isinstance(raw_region_value, str):
        raw_region = raw_region_value.strip()
    else:
        raw_region = ""
    if provider == "aws":
        # Treat "global" as a non-concrete hint for AWS and resolve to the
        # configured default region for concrete client/API operations.
        if not raw_region or raw_region == "global":
            return _default_aws_region()
        return raw_region
    return raw_region or "global"
