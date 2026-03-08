import pytest
from unittest.mock import MagicMock, patch
from fastapi import Request, Response
from app.shared.core.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TrustedProxyHeadersMiddleware,
)
from app.shared.core.config import Settings


@pytest.fixture
def mock_settings():
    with patch("app.shared.core.middleware.get_settings") as mock:
        mock.return_value = MagicMock(spec=Settings)
        mock.return_value.DEBUG = False
        mock.return_value.CORS_ORIGINS = ["https://app.example.com"]
        yield mock.return_value


@pytest.fixture
def mock_call_next():
    async def _call_next(request: Request):
        return Response(content=b"OK", media_type="text/plain")

    return _call_next


@pytest.mark.asyncio
async def test_security_headers_prod(mock_settings, mock_call_next):
    middleware = SecurityHeadersMiddleware(app=MagicMock())

    scope = {
        "type": "http",
        "scheme": "https",
        "server": ("testserver", 443),
        "method": "GET",
        "path": "/api/test",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope=scope)

    response = await middleware.dispatch(request, mock_call_next)

    headers = response.headers
    # HSTS
    assert (
        headers["Strict-Transport-Security"]
        == "max-age=31536000; includeSubDomains; preload"
    )
    # Anti-sniff
    assert headers["X-Content-Type-Options"] == "nosniff"
    # Frame Options
    assert headers["X-Frame-Options"] == "DENY"
    # CSP
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert (
        "https://app.example.com" in headers["Content-Security-Policy"]
    )  # connect-src check
    assert "'unsafe-inline'" not in headers["Content-Security-Policy"]
    assert "style-src-attr 'none'" in headers["Content-Security-Policy"]
    assert "object-src 'none'" in headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_security_headers_debug(mock_settings, mock_call_next):
    mock_settings.DEBUG = True
    middleware = SecurityHeadersMiddleware(app=MagicMock())

    scope = {
        "type": "http",
        "scheme": "https",
        "server": ("testserver", 443),
        "method": "GET",
        "path": "/api/test",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope=scope)

    response = await middleware.dispatch(request, mock_call_next)

    # HSTS disabled in debug
    assert response.headers["Strict-Transport-Security"] == "max-age=0"


@pytest.mark.asyncio
async def test_request_id_generation(mock_call_next):
    middleware = RequestIDMiddleware(app=MagicMock())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [],
    }
    request = Request(scope=scope)

    with patch("app.shared.core.middleware.set_correlation_id") as mock_set_ctx:
        response = await middleware.dispatch(request, mock_call_next)

        req_id = response.headers["X-Request-ID"]
        assert req_id is not None
        mock_set_ctx.assert_called_with(req_id)


@pytest.mark.asyncio
async def test_request_id_propagation(mock_call_next):
    middleware = RequestIDMiddleware(app=MagicMock())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [(b"x-request-id", b"custom-trace-123")],
    }
    request = Request(scope=scope)

    response = await middleware.dispatch(request, mock_call_next)

    assert response.headers["X-Request-ID"] == "custom-trace-123"


@pytest.mark.asyncio
async def test_trusted_proxy_headers_middleware_ignores_untrusted_forwarded_headers(
    mock_call_next,
):
    middleware = TrustedProxyHeadersMiddleware(app=MagicMock())

    scope = {
        "type": "http",
        "scheme": "http",
        "server": ("testserver", 80),
        "method": "GET",
        "path": "/api/test",
        "query_string": b"",
        "headers": [
            (b"x-forwarded-for", b"198.51.100.21"),
            (b"x-forwarded-proto", b"https"),
        ],
        "client": ("203.0.113.10", 44321),
    }
    request = Request(scope=scope)

    with patch("app.shared.core.middleware.get_settings") as mock_settings:
        mock_settings.return_value.TRUST_PROXY_HEADERS = False
        mock_settings.return_value.TRUSTED_PROXY_HOPS = 1
        mock_settings.return_value.TRUSTED_PROXY_CIDRS = ["203.0.113.10/32"]

        await middleware.dispatch(request, mock_call_next)

    assert request.client is not None
    assert request.client.host == "203.0.113.10"
    assert request.url.scheme == "http"
