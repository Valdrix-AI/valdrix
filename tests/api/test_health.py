import pytest
from httpx import AsyncClient
from app.shared.health import HealthService

@pytest.mark.asyncio
async def test_health_service_all_ok(db):
    service = HealthService(db)
    health = await service.check_all()
    
    assert health["status"] in ["healthy", "degraded"]
    assert health["database"]["status"] == "up"
    assert "latency_ms" in health["database"]
    assert "status" in health["redis"]
    assert "status" in health["aws"]

@pytest.mark.asyncio
async def test_health_endpoint(ac: AsyncClient):
    response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["database"]["status"] == "up"

@pytest.mark.asyncio
async def test_health_db_failure(ac: AsyncClient):
    # Mock DB failure
    from unittest.mock import patch
    with patch("sqlalchemy.ext.asyncio.AsyncSession.execute", side_effect=Exception("DB Down")):
        # Mock the service directly to be sure
        with patch("app.shared.health.HealthService.check_database", return_value=(False, {"error": "DB Down"})):
            response = await ac.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["database"]["status"] == "down"
