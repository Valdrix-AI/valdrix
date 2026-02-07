import pytest
from unittest.mock import MagicMock, patch
from starlette.responses import Response
from app.shared.core.middleware import SecurityHeadersMiddleware, RequestIDMiddleware

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
        assert headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains; preload"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert "content-security-policy" in headers.keys() or "Content-Security-Policy" in headers.keys()

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
