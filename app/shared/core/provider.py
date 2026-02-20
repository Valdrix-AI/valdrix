from __future__ import annotations

from typing import Any


SUPPORTED_PROVIDERS: set[str] = {
    "aws",
    "azure",
    "gcp",
    "saas",
    "license",
    "platform",
    "hybrid",
}


_CONNECTION_CLASS_HINTS: tuple[tuple[str, str], ...] = (
    ("aws", "aws"),
    ("azure", "azure"),
    ("gcp", "gcp"),
    ("saas", "saas"),
    ("license", "license"),
    ("platform", "platform"),
    ("hybrid", "hybrid"),
)


def normalize_provider(value: Any) -> str:
    """Return a canonical provider key or empty string when invalid/missing."""
    normalized = str(value or "").strip().lower()
    return normalized if normalized in SUPPORTED_PROVIDERS else ""


def resolve_provider_from_connection(connection: Any) -> str:
    """
    Resolve provider from connection models without AWS-only fallbacks.

    Priority:
    1. explicit `connection.provider` (preserved, even if not in built-in set)
    2. known class-name hints (`AWSConnection`, `AzureConnection`, ...)
    """
    explicit_value = getattr(connection, "provider", None)
    explicit_enum_value = getattr(explicit_value, "value", None)
    if isinstance(explicit_value, str):
        explicit_provider = explicit_value.strip().lower()
    elif isinstance(explicit_enum_value, str):
        explicit_provider = explicit_enum_value.strip().lower()
    else:
        explicit_provider = ""
    if explicit_provider:
        return explicit_provider

    # For test doubles (e.g. MagicMock(spec=AWSConnection)), __class__ points to
    # the spec class while type(connection) is still MagicMock.
    class_name = getattr(getattr(connection, "__class__", None), "__name__", "") or ""
    if not class_name:
        class_name = getattr(getattr(connection, "_spec_class", None), "__name__", "") or ""
    if not class_name:
        class_name = type(connection).__name__

    type_name = class_name.strip().lower()
    for needle, provider in _CONNECTION_CLASS_HINTS:
        if needle in type_name:
            return provider

    return ""
