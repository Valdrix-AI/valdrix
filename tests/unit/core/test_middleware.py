"""
Tests for app/shared/core/middleware.py - FastAPI middleware
"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import URL

from app.shared.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware


class TestRequestIDMiddleware:
    """Test RequestIDMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_request_id_middleware_adds_header(self):
        """Test that middleware adds X-Request-ID header."""
        middleware = RequestIDMiddleware(None)
        
        # Create mock request and response
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {}
        mock_request.state = AsyncMock()
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        mock_response.headers = {}
        call_next.return_value = mock_response
        
        # Call middleware
        response = await middleware.dispatch(mock_request, call_next)
        
        # Verify request ID was added to request state
        assert hasattr(mock_request.state, 'request_id')
        assert len(mock_request.state.request_id) > 0
        
        # Verify response header was added
        assert 'X-Request-ID' in response.headers
        assert response.headers['X-Request-ID'] == mock_request.state.request_id

    @pytest.mark.asyncio
    async def test_request_id_middleware_preserves_existing_header(self):
        """Test that middleware preserves existing X-Request-ID header."""
        middleware = RequestIDMiddleware(None)
        
        # Create mock request with existing request ID
        existing_request_id = "existing-request-123"
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {"X-Request-ID": existing_request_id}
        mock_request.state = AsyncMock()
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        mock_response.headers = {}
        call_next.return_value = mock_response
        
        # Call middleware
        response = await middleware.dispatch(mock_request, call_next)
        
        # Verify existing request ID was preserved
        assert mock_request.state.request_id == existing_request_id
        assert response.headers['X-Request-ID'] == existing_request_id

    @pytest.mark.asyncio
    async def test_request_id_middleware_generates_unique_ids(self):
        """Test that middleware generates unique request IDs."""
        middleware = RequestIDMiddleware(None)
        
        # Create multiple mock requests
        requests = []
        responses = []
        
        for i in range(3):
            mock_request = AsyncMock(spec=Request)
            mock_request.headers = {}
            mock_request.state = AsyncMock()
            
            call_next = AsyncMock()
            mock_response = AsyncMock(spec=Response)
            mock_response.headers = {}
            call_next.return_value = mock_response
            
            response = await middleware.dispatch(mock_request, call_next)
            requests.append(mock_request)
            responses.append(response)
        
        # Verify all request IDs are unique
        request_ids = [req.state.request_id for req in requests]
        assert len(set(request_ids)) == len(request_ids)  # All unique

    @pytest.mark.asyncio
    async def test_request_id_middleware_handles_call_next_exception(self):
        """Test that middleware handles exceptions from call_next."""
        middleware = RequestIDMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        mock_request.headers = {}
        mock_request.state = AsyncMock()
        
        call_next = AsyncMock()
        call_next.side_effect = Exception("Test exception")
        
        # Should propagate exception
        with pytest.raises(Exception, match="Test exception"):
            await middleware.dispatch(mock_request, call_next)


class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware functionality."""

    @pytest.mark.asyncio
    async def test_security_headers_middleware_adds_headers(self):
        """Test that middleware adds security headers."""
        # Fix: Patch get_settings to ensure controlled environment (DEBUG=False)
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            mock_settings.return_value.CORS_ORIGINS = []
            
            middleware = SecurityHeadersMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        # Fix: Use a proper object for URL that has a path attribute
        from starlette.datastructures import URL
        mock_request.url = URL("https://example.com/api/test")
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        mock_response.headers = {}
        call_next.return_value = mock_response
        
        # Call middleware
        response = await middleware.dispatch(mock_request, call_next)
        
        # Verify security headers are present
        security_headers = [
            'X-Content-Type-Options',
            'X-Frame-Options',
            'X-XSS-Protection',
            'Referrer-Policy',
            'Content-Security-Policy'
        ]
        
        for header in security_headers:
            assert header in response.headers

    @pytest.mark.asyncio
    async def test_security_headers_middleware_csp_header(self):
        """Test Content Security Policy header content."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            mock_settings.return_value.CORS_ORIGINS = []
            middleware = SecurityHeadersMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        mock_request.url = URL("https://example.com/api/test")
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        mock_response.headers = {}
        call_next.return_value = mock_response
        
        # Call middleware
        response = await middleware.dispatch(mock_request, call_next)
        
        csp = response.headers['Content-Security-Policy']
        
        # Verify CSP contains expected directives
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp

    @pytest.mark.asyncio
    async def test_security_headers_middleware_https_only_headers(self):
        """Test HTTPS-specific headers for HTTPS requests."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            middleware = SecurityHeadersMiddleware(None)
        
            # Test HTTPS request
            # Test HTTPS request
            mock_request = AsyncMock(spec=Request)
            mock_request.url = URL("https://example.com/api/test")
            
            call_next = AsyncMock()
            mock_response = AsyncMock(spec=Response)
            mock_response.headers = {}
            call_next.return_value = mock_response
            
            response = await middleware.dispatch(mock_request, call_next)
            
            # HTTPS requests should get HSTS
            assert 'Strict-Transport-Security' in response.headers
            hsts = response.headers['Strict-Transport-Security']
            assert 'max-age=31536000' in hsts  # 1 year
            assert 'includeSubDomains' in hsts

    @pytest.mark.asyncio
    async def test_security_headers_middleware_http_no_hsts(self):
        """Test that HTTP requests don't get HSTS header."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            middleware = SecurityHeadersMiddleware(None)
        
            # Test HTTP request
            # Test HTTP request
            mock_request = AsyncMock(spec=Request)
            mock_request.url = URL("http://example.com/api/test")
            
            call_next = AsyncMock()
            mock_response = AsyncMock(spec=Response)
            mock_response.headers = {}
            call_next.return_value = mock_response
            
            response = await middleware.dispatch(mock_request, call_next)
            
            # HTTP requests should not get HSTS
            assert 'Strict-Transport-Security' not in response.headers

    @pytest.mark.asyncio
    async def test_security_headers_middleware_preserves_existing_headers(self):
        """Test that middleware doesn't overwrite existing security headers."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            middleware = SecurityHeadersMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        mock_request.url = URL("https://example.com/api/test")
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        # Set existing security header
        mock_response.headers = {'X-Frame-Options': 'ALLOW-FROM https://trusted.com'}
        call_next.return_value = mock_response
        
        response = await middleware.dispatch(mock_request, call_next)
        
        # Should preserve existing header
        assert response.headers['X-Frame-Options'] == 'ALLOW-FROM https://trusted.com'

    @pytest.mark.asyncio
    async def test_security_headers_middleware_handles_call_next_exception(self):
        """Test that middleware handles exceptions from call_next."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            middleware = SecurityHeadersMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        mock_request.url = URL("https://example.com/api/test")
        
        call_next = AsyncMock()
        call_next.side_effect = Exception("Test exception")
        
        # Should propagate exception
        with pytest.raises(Exception, match="Test exception"):
            await middleware.dispatch(mock_request, call_next)

    @pytest.mark.asyncio
    async def test_security_headers_middleware_all_headers_present(self):
        """Test that all expected security headers are present."""
        with patch("app.shared.core.middleware.get_settings") as mock_settings:
            mock_settings.return_value.DEBUG = False
            mock_settings.return_value.CORS_ORIGINS = []
            middleware = SecurityHeadersMiddleware(None)
        
        mock_request = AsyncMock(spec=Request)
        mock_request.url = URL("https://example.com/api/test")
        
        call_next = AsyncMock()
        mock_response = AsyncMock(spec=Response)
        mock_response.headers = {}
        call_next.return_value = mock_response
        
        response = await middleware.dispatch(mock_request, call_next)
        
        from unittest.mock import ANY

        expected_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': ANY,
            'Strict-Transport-Security': ANY
        }
        
        for header, expected_value in expected_headers.items():
            assert header in response.headers
            if expected_value != ANY:
                assert response.headers[header] == expected_value
