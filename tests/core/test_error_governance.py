import json
import pytest
from unittest.mock import MagicMock, patch, ANY
from fastapi import Request
from app.shared.core.error_governance import handle_exception
from app.shared.core.exceptions import ValdrixException


@pytest.fixture
def mock_request():
    request = MagicMock(spec=Request)
    request.url.path = "/api/test"
    request.method = "GET"
    return request


@pytest.mark.asyncio
async def test_handle_valdrix_exception(mock_request):
    """Verify that handle_exception correctly processes a ValdrixException."""
    exc = ValdrixException(message="Test Error", code="test_error", status_code=400)

    with patch("app.shared.core.error_governance.tracer") as mock_tracer:
        # We need to mock the span context manager
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = (
            mock_span
        )

        response = handle_exception(mock_request, exc)

        assert response.status_code == 400
        data = response.body.decode()
        assert "test_error" in data
        assert "Test Error" in data

        # Verify OTel recording
        mock_span.set_attribute.assert_any_call("error.id", ANY)
        mock_span.set_attribute.assert_any_call("http.path", "/api/test")


@pytest.mark.asyncio
async def test_handle_generic_exception(mock_request):
    """Verify that ValueError is classified as a 400 business validation error."""
    exc = ValueError("Secret error")

    with patch("app.shared.core.error_governance.logger") as mock_logger:
        response = handle_exception(mock_request, exc)

        assert response.status_code == 400
        data = response.body.decode()
        assert "value_error" in data

        # Verify structured logging
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        assert kwargs["error"] == "Secret error"


@pytest.mark.asyncio
async def test_handle_valdrix_exception_sanitizes_unsafe_details_in_production(mock_request):
    exc = ValdrixException(
        message="db password leaked",
        code="db_error",
        status_code=500,
        details={"secret": "redact-me"},
    )

    with (
        patch("app.shared.core.config.get_settings", return_value=MagicMock(ENVIRONMENT="production")),
        patch("app.shared.core.error_governance.tracer") as mock_tracer,
    ):
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        response = handle_exception(mock_request, exc, error_id="err-prod-1")

        body = json.loads(response.body)
        assert response.status_code == 500
        assert body["error"]["code"] == "db_error"
        assert body["error"]["message"] == "An error occurred while processing your request"
        assert body["error"]["details"] is None


@pytest.mark.asyncio
async def test_handle_csrf_exception_parses_status_from_status_code_tuple_in_prod(mock_request):
    class CsrfProtectError(Exception):
        pass

    exc = CsrfProtectError("csrf tuple")
    exc.status_code = (419, "csrf")

    with patch(
        "app.shared.core.config.get_settings",
        return_value=MagicMock(ENVIRONMENT="production"),
    ):
        response = handle_exception(mock_request, exc, error_id="csrf-prod")

    body = json.loads(response.body)
    assert response.status_code == 419
    assert body["error"]["code"] == "csrf_error"
    assert body["error"]["message"] == "Invalid or missing CSRF token"


@pytest.mark.asyncio
async def test_handle_csrf_exception_parses_status_from_args_tuple_in_dev(mock_request):
    class CsrfProtectError(Exception):
        pass

    exc = CsrfProtectError((422, "bad token"))

    with patch(
        "app.shared.core.config.get_settings",
        return_value=MagicMock(ENVIRONMENT="development"),
    ):
        response = handle_exception(mock_request, exc, error_id="csrf-dev")

    body = json.loads(response.body)
    assert response.status_code == 422
    assert body["error"]["code"] == "csrf_error"
    assert "422" in body["error"]["message"]


@pytest.mark.asyncio
async def test_handle_csrf_exception_parses_status_from_args_int(mock_request):
    class CsrfProtectError(Exception):
        pass

    exc = CsrfProtectError(401, "missing token")

    with patch(
        "app.shared.core.config.get_settings",
        return_value=MagicMock(ENVIRONMENT="development"),
    ):
        response = handle_exception(mock_request, exc, error_id="csrf-args-int")

    body = json.loads(response.body)
    assert response.status_code == 401
    assert body["error"]["code"] == "csrf_error"


@pytest.mark.asyncio
async def test_handle_unhandled_exception_uses_internal_error_and_logs_exception(
    mock_request,
):
    exc = RuntimeError("secret internal cause")

    with (
        patch(
            "app.shared.core.config.get_settings",
            return_value=MagicMock(ENVIRONMENT="development"),
        ),
        patch("app.shared.core.error_governance.logger") as mock_logger,
    ):
        response = handle_exception(mock_request, exc, error_id="unhandled-1")

    body = json.loads(response.body)
    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["message"] == "An unexpected internal error occurred"
    mock_logger.exception.assert_called_once()


@pytest.mark.asyncio
async def test_handle_exception_records_raw_exception_when_valdrix_otel_hook_missing(
    mock_request,
):
    class FakeValdrixException(Exception):
        def __init__(
            self,
            message: str,
            code: str = "internal_error",
            status_code: int = 500,
            details: dict | None = None,
        ) -> None:
            self.message = message
            self.code = code
            self.status_code = status_code
            self.details = details or {}

    exc = ValueError("bad payload")

    with (
        patch(
            "app.shared.core.config.get_settings",
            return_value=MagicMock(ENVIRONMENT="development"),
        ),
        patch("app.shared.core.error_governance.ValdrixException", FakeValdrixException),
        patch("app.shared.core.error_governance.tracer") as mock_tracer,
    ):
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        response = handle_exception(mock_request, exc, error_id="otel-fallback")

    body = json.loads(response.body)
    assert response.status_code == 400
    assert body["error"]["code"] == "value_error"
    mock_span.record_exception.assert_called_once_with(exc)
    mock_span.set_status.assert_called_once()
