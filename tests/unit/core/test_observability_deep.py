import os
import pytest
from unittest.mock import MagicMock, patch
import sys

# Crucial: Mock sentry_sdk in sys.modules BEFORE anything imports it
mock_sentry_sdk = MagicMock()
sys.modules["sentry_sdk"] = mock_sentry_sdk
sys.modules["sentry_sdk.integrations.fastapi"] = MagicMock()
sys.modules["sentry_sdk.integrations.sqlalchemy"] = MagicMock()
sys.modules["sentry_sdk.integrations.logging"] = MagicMock()

# Import the module under test AFTER mocking sys.modules
import app.shared.core.sentry as sentry_module
from app.shared.core.sentry import (
    init_sentry,
    _before_send,
    capture_message,
    set_user,
    set_tenant_context
)
from app.shared.core.tracing import (
    get_current_trace_id,
    set_correlation_id
)

class TestObservabilityDeep:
    """Deep tests for sentry.py and tracing.py to reach 100% coverage."""

    def setup_method(self):
        # Ensure sentry_sdk and integrations are defined in the module's globals
        if not hasattr(sentry_module, 'sentry_sdk') or sentry_module.sentry_sdk is None:
            sentry_module.sentry_sdk = mock_sentry_sdk
        
        # Inject integrations into the module namespace to avoid NameError
        sentry_module.FastApiIntegration = MagicMock
        sentry_module.SqlalchemyIntegration = MagicMock
        sentry_module.LoggingIntegration = MagicMock
        sentry_module.SENTRY_AVAILABLE = True

    def test_init_sentry_no_dsn(self):
        """Test sentry init fails without DSN."""
        with patch.dict(os.environ, {"SENTRY_DSN": ""}):
            assert init_sentry() is False

    def test_init_sentry_success(self):
        """Test sentry init success with DSN."""
        with patch.dict(os.environ, {"SENTRY_DSN": "https://test@sentry.io/1", "ENVIRONMENT": "production"}):
            with patch.object(sentry_module.sentry_sdk, 'init') as mock_init:
                init_sentry()
                assert mock_init.called

    def test_before_send_filter_health(self):
        """Test Sentry filter drops health check errors."""
        event = {"request": {"url": "http://localhost/health"}}
        assert _before_send(event, None) is None

    def test_before_send_enrich_trace(self):
        """Test Sentry filter enriches events with trace ID."""
        event = {"request": {"url": "http://localhost/api/v1/data"}}
        with patch("app.shared.core.tracing.get_current_trace_id", return_value="test-trace-123"):
            result = _before_send(event, None)
            assert result["tags"]["trace_id"] == "test-trace-123"

    def test_capture_message_sentry(self):
        """Test capture_message sends event to Sentry."""
        # Use patch.object to ensure we're patching the exact object the module is using
        with patch.object(sentry_module.sentry_sdk, 'capture_message') as mock_capture:
            capture_message("test message", level="error")
            assert mock_capture.called

    def test_set_user_sentry(self):
        """Test set_user updates Sentry context."""
        with patch.object(sentry_module.sentry_sdk, 'set_user') as mock_set:
            set_user("u1", "t1", "test@example.com")
            assert mock_set.called
            assert mock_set.call_args[0][0]["id"] == "u1"

    def test_set_tenant_context_sentry(self):
        """Test set_tenant_context updates Sentry tags."""
        with patch.object(sentry_module.sentry_sdk, 'set_tag') as mock_set:
            set_tenant_context("t1", "Tenant Name")
            assert mock_set.called

    def test_tracing_correlation_id(self):
        """Test tracing correlation ID set logic."""
        with patch("opentelemetry.trace.get_current_span") as mock_span:
            set_correlation_id("corr-123")
            assert mock_span.return_value.set_attribute.called
