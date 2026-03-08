"""Observability-specific settings validation helpers."""

from __future__ import annotations


def _normalize_environment(value: object) -> str:
    return str(value or "").strip().lower()


def validate_observability_config(
    settings_obj: object,
    *,
    env_production: str,
    env_staging: str,
) -> None:
    """Require enterprise telemetry sinks and forbid public schema exposure."""
    environment = _normalize_environment(getattr(settings_obj, "ENVIRONMENT", ""))
    strict_env = environment in {env_production, env_staging}
    if not strict_env:
        return

    otlp_endpoint = str(
        getattr(settings_obj, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or ""
    ).strip()
    if otlp_endpoint and not otlp_endpoint.startswith(("http://", "https://")):
        raise ValueError(
            "OTEL_EXPORTER_OTLP_ENDPOINT must use an explicit http:// or https:// URL."
        )

    if otlp_endpoint and not bool(getattr(settings_obj, "OTEL_LOGS_EXPORT_ENABLED", True)):
        raise ValueError(
            "OTEL_LOGS_EXPORT_ENABLED must remain true when OTLP export is configured."
        )

    sentry_dsn = str(getattr(settings_obj, "SENTRY_DSN", "") or "").strip()
    if sentry_dsn and not sentry_dsn.startswith(("http://", "https://")):
        raise ValueError("SENTRY_DSN must use an explicit http:// or https:// URL.")

    if bool(getattr(settings_obj, "EXPOSE_API_DOCUMENTATION_PUBLICLY", False)):
        raise ValueError(
            "EXPOSE_API_DOCUMENTATION_PUBLICLY must be false in staging/production."
        )


__all__ = ["validate_observability_config"]
