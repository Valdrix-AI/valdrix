import sys
import structlog
import logging
from app.shared.core.config import get_settings

def pii_redactor(_logger, _method_name, event_dict):
    """
    Recursively redact common PII and sensitive fields from logs.
    Ensures GDPR/SOC2 compliance by preventing leakage into telemetry.
    """
    import re
    email_regex = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    phone_regex = re.compile(r"\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}")
    pii_fields = {"password", "token", "key", "secret", "authorization", "auth", "api_key", "ssn", "credit_card", "cc_number"}

    def redact_text(text):
        if not isinstance(text, str):
            return text
        text = email_regex.sub("[EMAIL_REDACTED]", text)
        # Only redact phone if it looks long enough to be an actual number
        # to avoid redacting random small numbers
        if len(re.findall(r"\d", text)) >= 7:
            text = phone_regex.sub("[PHONE_REDACTED]", text)
        return text

    def redact_recursive(data):
        if isinstance(data, dict):
            return {
                k: ("[REDACTED]" if str(k).lower() in pii_fields else redact_recursive(v))
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [redact_recursive(item) for item in data]
        elif isinstance(data, str):
            return redact_text(data)
        return data

    return redact_recursive(event_dict)


def add_otel_trace_id(_logger, _method_name, event_dict):
    """Integrate OTel Trace IDs into structured logs."""
    from app.shared.core.tracing import get_current_trace_id
    trace_id = get_current_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict

def setup_logging():
    settings = get_settings()

    # 1. Choose the renderer based on environment
    if settings.DEBUG:
        renderer = structlog.dev.ConsoleRenderer()
        min_level = logging.DEBUG
    else:
        renderer = structlog.processors.JSONRenderer()
        min_level = logging.INFO

    # 2. Configure the "Processors" (The Middleware Pipeline for Logs)
    processors = [
        structlog.contextvars.merge_contextvars, # Support async context
        structlog.processors.add_log_level,      # Add "level": "info"
        structlog.processors.TimeStamper(fmt="iso"), # Add "timestamp": "2026..."
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,    # Render exceptions nicely
        add_otel_trace_id,                       # Observability: Add Trace IDs
        pii_redactor,                            # Security: Redact PII before rendering
        renderer
    ]


    # 3. Configure the logger or apply the configuration
    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 4. Intercept the standard logging (e.g. uvicorn's internal log).
    # This ensure even library logs get formatted as JSON.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        # filename="debug.log",
        level=min_level,
    )


def audit_log(event: str, user_id: str, tenant_id: str, details: dict = None):
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
