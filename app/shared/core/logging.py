import sys
import structlog
import logging
from typing import Any, cast
from app.shared.core.config import get_settings


def pii_redactor(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Recursively redact common PII and sensitive fields from logs.
    Ensures GDPR/SOC2 compliance by preventing leakage into telemetry.
    """
    import re

    email_regex = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    phone_regex = re.compile(
        r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)"
    )
    pii_fields = {
        "password",
        "token",
        "secret",
        "authorization",
        "auth",
        "api_key",
        "apikey",
        "ssn",
        "credit_card",
        "cc_number",
        "access_token",
        "refresh_token",
        "client_secret",
        "private_key",
        "x_api_key",
    }
    pii_suffixes = ("_token", "_secret", "_password", "_key")
    pii_contains = ("authorization", "secret", "token", "apikey", "api_key")

    def is_sensitive_key(key: Any) -> bool:
        key_str = str(key).lower().strip()
        key_norm = key_str.replace("-", "_")
        if key_norm in pii_fields:
            return True
        if key_norm.endswith(pii_suffixes):
            return True
        tokens = [t for t in re.split(r"[^a-z0-9]+", key_norm) if t]
        if any(t in pii_fields for t in tokens):
            return True
        return any(fragment in key_norm for fragment in pii_contains)

    def redact_text(text: Any) -> Any:
        if not isinstance(text, str):
            return text
        text = email_regex.sub("[EMAIL_REDACTED]", text)

        # Redact only plausible phone numbers (avoid timestamps/UUID fragments).
        def _replace_phone(match: re.Match[str]) -> str:
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            looks_like_phone = len(digits) >= 10 and (
                candidate.strip().startswith("+")
                or any(ch in candidate for ch in (" ", "-", ".", "(", ")"))
            )
            return "[PHONE_REDACTED]" if looks_like_phone else candidate

        text = phone_regex.sub(_replace_phone, text)
        return text

    def redact_recursive(data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: ("[REDACTED]" if is_sensitive_key(k) else redact_recursive(v))
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [redact_recursive(item) for item in data]
        elif isinstance(data, str):
            return redact_text(data)
        return data

    redacted = redact_recursive(event_dict)
    if isinstance(redacted, dict):
        return cast(dict[str, Any], redacted)
    return {}


def add_otel_trace_id(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Integrate OTel Trace IDs into structured logs."""
    from app.shared.core.tracing import get_current_trace_id

    trace_id = get_current_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def setup_logging() -> None:
    settings = get_settings()

    # 1. Configure the common processors (Middleware Pipeline for Logs)
    base_processors = [
        structlog.contextvars.merge_contextvars,  # Support async context
        structlog.processors.add_log_level,  # Add "level": "info"
        structlog.processors.TimeStamper(fmt="iso"),  # Add "timestamp": "2026..."
        structlog.processors.StackInfoRenderer(),
        add_otel_trace_id,  # Observability: Add Trace IDs
        pii_redactor,  # Security: Redact PII before rendering
    ]

    # 2. Choose the renderer based on environment
    if settings.DEBUG:
        renderer: Any = structlog.dev.ConsoleRenderer()
        processors = base_processors + [renderer]
        min_level = logging.DEBUG
    else:
        renderer = structlog.processors.JSONRenderer()
        processors = base_processors + [structlog.processors.dict_tracebacks, renderer]
        min_level = logging.INFO

    # 3. Configure the logger or apply the configuration
    structlog.configure(
        processors=cast(Any, processors),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # 4. Intercept the standard logging (e.g. uvicorn's internal log).
    # This ensure even library logs get formatted as JSON.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        # filename="debug.log",
        level=min_level,
    )


def audit_log(
    event: str,
    user_id: str,
    tenant_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    """
    Standardized helper for security-critical audit events.
    Enforces a consistent schema for SIEM ingestion.
    """
    logger = structlog.get_logger("audit")
    logger.info(
        event,
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        metadata=details or {},
    )
