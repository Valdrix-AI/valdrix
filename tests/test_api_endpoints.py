import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for /health endpoint."""
    
    async def test_health_returns_200(self, ac: AsyncClient):
        """Test that health endpoint returns 200."""
        response = await ac.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]
        assert "database" in data
        assert data["database"]["status"] == "up"


@pytest.mark.asyncio
class TestCostsEndpoint:
    """Tests for /costs endpoint."""
    
    async def test_costs_without_auth_returns_401(self, ac: AsyncClient):
        """Test that costs endpoint requires authentication."""
        response = await ac.get("/api/v1/costs?start_date=2026-01-01&end_date=2026-01-02")
        
        # FastAPI returns 401 for missing header with HTTPBearer
        assert response.status_code == 401
    
    async def test_costs_with_invalid_token_returns_401(self, ac: AsyncClient):
        """Test that invalid token is rejected."""
        response = await ac.get(
            "/api/v1/costs?start_date=2026-01-01&end_date=2026-01-02",
            headers={"Authorization": "Bearer invalid-token-12345"}
        )
        
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAnalyzeEndpoint:
    """Tests for /analyze endpoint."""
    
    async def test_analyze_without_auth_returns_401(self, ac: AsyncClient):
        """Test that analyze endpoint requires authentication."""
        # /api/v1/costs/analyze is a POST endpoint
        response = await ac.post("/api/v1/costs/analyze")
        
        assert response.status_code == 401


@pytest.mark.asyncio
class TestLLMUsageEndpoint:
    """Tests for /llm/usage endpoint."""
    
    async def test_llm_usage_without_auth_returns_401(self, ac: AsyncClient):
        """Test that LLM usage endpoint requires authentication."""
        response = await ac.get("/api/v1/costs/llm/usage")
        
        assert response.status_code == 401


@pytest.mark.asyncio
class TestCarbonEndpoint:
    """Tests for /carbon endpoint."""
    
    async def test_carbon_without_auth_returns_401(self, ac: AsyncClient):
        """Test that carbon endpoint requires authentication.
        
        Note: FastAPI validates query params before auth. If params are valid,
        we get 401. If invalid, we'd get 422.
        """
        response = await ac.get("/api/v1/carbon?start_date=2026-01-01&end_date=2026-01-02")
        
        # FastAPI 422 = validation error before auth check, 401 = auth check
        assert response.status_code in [401, 422]


@pytest.mark.asyncio
class TestZombiesEndpoint:
    """Tests for /zombies endpoints."""
    
    async def test_zombies_without_auth_returns_401(self, ac: AsyncClient):
        """Test that zombies endpoint requires authentication."""
        response = await ac.get("/api/v1/zombies")
        
        assert response.status_code == 401
    
    async def test_zombies_request_without_auth_returns_401(self, ac: AsyncClient):
        """Test that zombie request endpoint requires authentication."""
        response = await ac.post(
            "/api/v1/zombies/request",
            json={
                "resource_id": "test-123", 
                "resource_type": "volume",
                "action": "delete_volume",
                "estimated_savings": 10.0
            }
        )
        
        assert response.status_code == 401
    
    async def test_zombies_approve_without_auth_returns_401(self, ac: AsyncClient):
        """Test that zombie approve endpoint requires authentication."""
        from uuid import uuid4
        response = await ac.post(f"/api/v1/zombies/approve/{uuid4()}")
        
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAdminEndpoint:
    """Tests for admin endpoints."""
    
    async def test_admin_trigger_without_key_returns_422(self, ac: AsyncClient):
        """Test that admin trigger requires X-Admin-Key header."""
        response = await ac.post("/api/v1/admin/trigger-analysis")
        
        # FastAPI returns 422 if required Header is missing
        assert response.status_code == 422


@pytest.mark.asyncio
class TestConnectionsEndpoint:
    """Tests for /connections endpoints."""
    
    async def test_sync_org_without_auth_returns_401(self, ac: AsyncClient):
        """Test that sync-org endpoint requires authentication."""
        from uuid import uuid4
        response = await ac.post(f"/api/v1/settings/connections/aws/{uuid4()}/sync-org")
        assert response.status_code == 401

    async def test_list_discovered_without_auth_returns_401(self, ac: AsyncClient):
        """Test that list discovered accounts endpoint requires authentication."""
        response = await ac.get("/api/v1/settings/connections/aws/discovered") # Added /settings
        assert response.status_code == 401
        
    async def test_link_discovered_without_auth_returns_401(self, ac: AsyncClient):
        """Test that link discovered account endpoint requires authentication."""
        from uuid import uuid4
        response = await ac.post(f"/api/v1/settings/connections/aws/discovered/{uuid4()}/link") # Added /settings
        assert response.status_code == 401
