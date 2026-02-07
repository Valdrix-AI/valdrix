import pytest
from httpx import AsyncClient

from unittest.mock import patch

@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Test root endpoint returns status ok."""
    response = await async_client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_health_live(async_client: AsyncClient):
    """Test Liveness probe."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_health_detailed(async_client: AsyncClient):
    """Test full health check endpoint."""
    with patch("app.shared.core.health.HealthService.check_all") as mock_check:
        mock_check.return_value = {
            "status": "healthy",
            "database": {"status": "up"},
            "redis": {"status": "up"},
            "aws": {"status": "up"}
        }
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_not_found(async_client: AsyncClient):
    """Test 404 handler."""
    response = await async_client.get("/api/v1/nonexistent")
    assert response.status_code == 404
