import pytest
from unittest.mock import MagicMock, patch
from starlette.responses import Response
from app.shared.core.middleware import (
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
    TrustedProxyHeadersMiddleware,
)


@pytest.fixture
def mock_app():
    async def app(scope, receive, send):
        response = Response("ok")
        await response(scope, receive, send)

    return app


@pytest.mark.asyncio
async def test_security_headers_middleware():
    """Test HSTS, CSP, and security headers injection."""

    async def call_next(request):
        return Response("ok")

    middleware = SecurityHeadersMiddleware(MagicMock())

    # Mock settings
    with patch("app.shared.core.middleware.get_settings") as mock_settings:
        mock_settings.return_value.DEBUG = False
        mock_settings.return_value.CORS_ORIGINS = ["https://example.com"]

        # HTTPS Request
        request = MagicMock()
        request.url.scheme = "https"
        request.url.path = "/api/v1/test"

        response = await middleware.dispatch(request, call_next)

        headers = response.headers
        assert (
            headers["Strict-Transport-Security"]
            == "max-age=31536000; includeSubDomains; preload"
        )
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert (
            "content-security-policy" in headers.keys()
            or "Content-Security-Policy" in headers.keys()
        )
        csp = headers.get("Content-Security-Policy") or headers.get("content-security-policy")
        assert csp is not None
        assert "'unsafe-inline'" not in csp
        assert "style-src-attr 'none'" in csp


@pytest.mark.asyncio
async def test_request_id_middleware():
    """Test request ID injection and correlation."""

    async def call_next(request):
        assert hasattr(request.state, "request_id")
        return Response("ok")

    middleware = RequestIDMiddleware(MagicMock())

    request = MagicMock()
    request.headers = {}
    request.state = MagicMock()

    with patch("app.shared.core.middleware.set_correlation_id") as mock_set_id:
        response = await middleware.dispatch(request, call_next)

        assert "X-Request-ID" in response.headers
        mock_set_id.assert_called_once()


@pytest.mark.asyncio
async def test_request_id_middleware_replaces_invalid_client_value():
    async def call_next(request):
        assert hasattr(request.state, "request_id")
        return Response("ok")

    middleware = RequestIDMiddleware(MagicMock())

    request = MagicMock()
    request.headers = {"X-Request-ID": "bad\nrequest"}
    request.state = MagicMock()

    with patch("app.shared.core.middleware.set_correlation_id") as mock_set_id:
        response = await middleware.dispatch(request, call_next)

        assert response.headers["X-Request-ID"] != "bad\nrequest"
        mock_set_id.assert_called_once_with(response.headers["X-Request-ID"])


@pytest.mark.asyncio
async def test_trusted_proxy_headers_middleware_normalizes_client_and_scheme():
    async def call_next(request):
        assert request.client is not None
        assert request.client.host == "198.51.100.21"
        assert request.scope["scheme"] == "https"
        return Response("ok")

    middleware = TrustedProxyHeadersMiddleware(MagicMock())

    with patch("app.shared.core.middleware.get_settings") as mock_settings:
        mock_settings.return_value.TRUST_PROXY_HEADERS = True
        mock_settings.return_value.TRUSTED_PROXY_HOPS = 1
        mock_settings.return_value.TRUSTED_PROXY_CIDRS = ["203.0.113.10/32"]

        from fastapi import Request

        request = Request(
            {
                "type": "http",
                "scheme": "http",
                "method": "GET",
                "path": "/api/v1/test",
                "headers": [
                    (b"x-forwarded-for", b"198.51.100.20, 198.51.100.21"),
                    (b"x-forwarded-proto", b"http, https"),
                ],
                "client": ("203.0.113.10", 44321),
            }
        )

        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 200
