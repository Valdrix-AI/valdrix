from unittest.mock import MagicMock, patch
from app.shared.core.logging import (
    pii_redactor,
    add_otel_trace_id,
    audit_log,
    setup_logging,
)


def test_pii_redactor_nested():
    """Verify recursive PII redaction for SOC2 compliance."""
    event_dict = {
        "user_id": 123,
        "email": "pii@example.com",
        "nested": {"token": "secret_123", "safe": "data"},
        "list": [{"password": "pass"}, "safe_item"],
    }

    redacted = pii_redactor(None, None, event_dict)

    # Email is regex-redacted in the value, not key-based
    assert redacted["email"] == "[EMAIL_REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "data"
    assert redacted["list"][0]["password"] == "[REDACTED]"
    assert redacted["list"][1] == "safe_item"


def test_pii_redactor_regex():
    """Verify regex-based PII redaction for unstructured text in logs."""
    event_dict = {
        "event": "User login failed for admin@example.com from +234 803 123 4567",
        "details": "Contact support at help@valdrics.ai",
    }

    redacted = pii_redactor(None, None, event_dict)

    assert "admin@example.com" not in redacted["event"]
    assert "[EMAIL_REDACTED]" in redacted["event"]
    assert "+234 803 123 4567" not in redacted["event"]
    assert "[PHONE_REDACTED]" in redacted["event"]
    assert "help@valdrics.ai" not in redacted["details"]
    assert "[EMAIL_REDACTED]" in redacted["details"]


def test_add_otel_trace_id():
    """Verify trace ID injection from tracing context."""
    with patch(
        "app.shared.core.tracing.get_current_trace_id", return_value="trace-123"
    ):
        result = add_otel_trace_id(None, None, {"event": "test"})
        assert result["trace_id"] == "trace-123"

    with patch("app.shared.core.tracing.get_current_trace_id", return_value=None):
        result = add_otel_trace_id(None, None, {"event": "test"})
        assert "trace_id" not in result


def test_audit_log_schema():
    """Verify audit log helper enforces the SIEM-friendly schema."""
    with patch("structlog.get_logger") as mock_get_logger:
        mock_audit_logger = MagicMock()
        mock_get_logger.return_value = mock_audit_logger

        audit_log("user_login", "u1", "t1", {"ip": "1.1.1.1"})

        mock_audit_logger.info.assert_called_with(
            "user_login", user_id="u1", tenant_id="t1", metadata={"ip": "1.1.1.1"}
        )


def test_setup_logging_no_crash():
    """Verify logging setup runs for both Debug and Prod modes."""
    with (
        patch("app.shared.core.logging.get_settings") as mock_settings,
        patch("app.shared.core.logging.configure_otlp_log_export") as mock_otlp,
    ):
        # 1. Debug (Console)
        mock_settings.return_value.DEBUG = True
        mock_settings.return_value.TESTING = False
        mock_settings.return_value.OTEL_EXPORTER_OTLP_ENDPOINT = ""
        setup_logging()

        # 2. Prod (JSON)
        mock_settings.return_value.DEBUG = False
        mock_settings.return_value.OTEL_EXPORTER_OTLP_ENDPOINT = (
            "http://otel-collector:4317"
        )
        setup_logging()
        assert mock_otlp.called
