import pytest
import os
import sys
from unittest.mock import MagicMock, patch

# Mock sentry_sdk before it's even imported anywhere
sys.modules["sentry_sdk"] = MagicMock()
sys.modules["sentry_sdk.integrations.fastapi"] = MagicMock()
sys.modules["sentry_sdk.integrations.sqlalchemy"] = MagicMock()
sys.modules["sentry_sdk.integrations.logging"] = MagicMock()

from app.shared.core.sentry import init_sentry, _before_send, capture_message, set_user, set_tenant_context

class TestSentryDeep:
    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    def test_init_sentry_success(self):
        with patch.dict(os.environ, {"SENTRY_DSN": "http://test@sentry.io/1"}):
            import sentry_sdk
            result = init_sentry()
            assert result is True
            assert sentry_sdk.init.called

    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", False)
    def test_init_sentry_unavailable(self):
        result = init_sentry()
        assert result is False

    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    def test_init_sentry_no_dsn(self):
        with patch.dict(os.environ, {}, clear=True):
            if "SENTRY_DSN" in os.environ:
                del os.environ["SENTRY_DSN"]
            result = init_sentry()
            assert result is False

    def test_before_send_filter_health(self):
        event = {"request": {"url": "http://localhost/health"}}
        result = _before_send(event, None)
        assert result is None

    def test_before_send_enrich_trace(self):
        event = {"request": {"url": "http://localhost/api/v1/test"}}
        with patch("app.shared.core.tracing.get_current_trace_id", return_value="trace-123"):
            result = _before_send(event, None)
            assert result["tags"]["trace_id"] == "trace-123"

    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    def test_capture_message(self):
        import sentry_sdk
        mock_scope = MagicMock()
        sentry_sdk.push_scope.return_value.__enter__.return_value = mock_scope
        
        capture_message("test message", level="error", extra_key="extra_val")
        
        mock_scope.set_extra.assert_called_with("extra_key", "extra_val")
        sentry_sdk.capture_message.assert_called_with("test message", "error")

    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    def test_set_user(self):
        import sentry_sdk
        set_user("user-1", tenant_id="tenant-1", email="test@test.com")
        sentry_sdk.set_user.assert_called_with({
            "id": "user-1",
            "tenant_id": "tenant-1",
            "email": "test@test.com"
        })

    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    def test_set_tenant_context(self):
        import sentry_sdk
        set_tenant_context("tenant-123", "Tenant Name")
        assert sentry_sdk.set_tag.call_count >= 2
        sentry_sdk.set_tag.assert_any_call("tenant_id", "tenant-123")
        sentry_sdk.set_tag.assert_any_call("tenant_name", "Tenant Name")
