import sys
import types
from unittest.mock import MagicMock, patch

import app.shared.core.sentry as sentry_module
from app.shared.core.sentry import (
    _before_send,
    capture_message,
    set_user,
    set_tenant_context,
)


def test_before_send_handles_missing_trace_import():
    event = {"request": {"url": "http://localhost/api"}}

    original = sys.modules.get("app.shared.core.tracing")
    sys.modules["app.shared.core.tracing"] = types.SimpleNamespace()
    try:
        result = _before_send(event, None)
        assert "tags" not in result or "trace_id" not in result.get("tags", {})
    finally:
        if original is None:
            del sys.modules["app.shared.core.tracing"]
        else:
            sys.modules["app.shared.core.tracing"] = original


def test_capture_message_noop_when_unavailable():
    with (
        patch.object(sentry_module, "SENTRY_AVAILABLE", False),
        patch.object(sentry_module, "sentry_sdk", MagicMock(), create=True) as mock_sdk,
    ):
        capture_message("hello", level="warning")
        mock_sdk.capture_message.assert_not_called()


def test_set_user_noop_when_unavailable():
    with (
        patch.object(sentry_module, "SENTRY_AVAILABLE", False),
        patch.object(sentry_module, "sentry_sdk", MagicMock(), create=True) as mock_sdk,
    ):
        set_user("user-1", tenant_id="tenant-1")
        mock_sdk.set_user.assert_not_called()


def test_set_tenant_context_noop_when_unavailable():
    with (
        patch.object(sentry_module, "SENTRY_AVAILABLE", False),
        patch.object(sentry_module, "sentry_sdk", MagicMock(), create=True) as mock_sdk,
    ):
        set_tenant_context("tenant-1")
        mock_sdk.set_tag.assert_not_called()
