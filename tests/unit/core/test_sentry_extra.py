from unittest.mock import patch

from app.shared.core.sentry import _before_send


def test_before_send_drops_health():
    event = {"request": {"url": "http://localhost/health"}}
    assert _before_send(event, {}) is None


def test_before_send_adds_trace_id():
    event = {"request": {"url": "http://localhost/api"}}
    with patch("app.shared.core.tracing.get_current_trace_id", return_value="trace-123"):
        result = _before_send(event, {})
    assert result["tags"]["trace_id"] == "trace-123"
