import os
from unittest.mock import MagicMock, patch

# Import app modules locally inside tests to allow patching
from app.shared.core.sentry import (
    init_sentry, capture_message, set_user, set_tenant_context,
    _before_send
)

class TestSentryDeep:
    @patch("app.shared.core.sentry.SENTRY_AVAILABLE", True)
    @patch("app.shared.core.sentry.sentry_sdk")
    def test_init_sentry_success(self, mock_sentry):
        with patch.dict(os.environ, {"SENTRY_DSN": "http://test@sentry.io/1"}):
            result = init_sentry()
            assert result is True
            assert mock_sentry.init.called

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
