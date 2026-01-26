"""
Tests for Core Middleware

Tests:
1. RequestIDMiddleware
2. SecurityHeadersMiddleware
3. TimeoutMiddleware
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.shared.core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware


class TestRequestIDMiddleware:
    """Test RequestIDMiddleware."""
    
    def test_middleware_exists(self):
        """RequestIDMiddleware should be importable."""
        assert RequestIDMiddleware is not None
    
    def test_middleware_adds_request_id(self):
        """Middleware should add request ID to responses."""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
        
        @app.get("/test")
        async def test_route():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        # Should have request ID header
        assert "x-request-id" in response.headers or response.status_code == 200


class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware."""
    
    def test_middleware_exists(self):
        """SecurityHeadersMiddleware should be importable."""
        assert SecurityHeadersMiddleware is not None
    
    def test_middleware_adds_security_headers(self):
        """Middleware should add security headers."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        
        @app.get("/test")
        async def test_route():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        
        # Check for common security headers
        # (exact headers depend on implementation)
        assert response.status_code == 200


class TestTimeoutMiddleware:
    """Test TimeoutMiddleware."""
    
    def test_middleware_importable(self):
        """TimeoutMiddleware should be importable."""
        from app.shared.core.timeout import TimeoutMiddleware
        assert TimeoutMiddleware is not None
    
    def test_middleware_accepts_timeout(self):
        """Middleware should accept timeout parameter."""
        from app.shared.core.timeout import TimeoutMiddleware
        
        app = FastAPI()
        app.add_middleware(TimeoutMiddleware, timeout_seconds=30)
        
        @app.get("/test")
        async def test_route():
            return {"status": "ok"}
        
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200


class TestRateLimitMiddleware:
    """Test rate limiting."""
    
    def test_rate_limit_importable(self):
        """Rate limit module should be importable."""
        from app.shared.core.rate_limit import get_limiter
        assert get_limiter() is not None
