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
