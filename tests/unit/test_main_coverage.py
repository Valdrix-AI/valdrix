import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def mock_lifespan_deps():
    with patch("os.makedirs") as mock_makedirs, \
         patch("app.main.EmissionsTracker") as mock_tracker, \
         patch("app.modules.governance.domain.scheduler.SchedulerService") as mock_scheduler, \
         patch("app.main.engine") as mock_engine:
        mock_engine.dispose = AsyncMock()
        yield {
            "makedirs": mock_makedirs,
            "tracker": mock_tracker.return_value,
            "scheduler": mock_scheduler.return_value,
            "dispose": mock_engine.dispose
        }

@pytest.mark.asyncio
async def test_lifespan_flow(mock_lifespan_deps):
    """Test app lifespan setup and teardown."""
    from app.main import lifespan, app
    
    async with lifespan(app):
        mock_lifespan_deps["makedirs"].assert_called_with("data", exist_ok=True)
    
    mock_lifespan_deps["dispose"].assert_called_once()

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_liveness_endpoint(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_health_check_healthy(client):
    mock_health = {
        "status": "healthy",
        "database": {"status": "up"},
        "redis": {"status": "up"},
        "aws": {"status": "up"}
    }
    with patch("app.shared.core.health.HealthService.check_all", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = mock_health
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

def test_valdrix_exception_handler(client):
    from app.main import app
    from app.shared.core.exceptions import ValdrixException
    
    @app.get("/test-valdrix-exc")
    async def trigger_exc():
        raise ValdrixException(message="Test message", code="test_code", status_code=418)
    
    response = client.get("/test-valdrix-exc")
    assert response.status_code == 418
    assert response.json()["code"] == "test_code"

def test_generic_exception_handler(client):
    from app.main import app
    
    @app.get("/test-generic-exc")
    async def trigger_exc():
        raise Exception("Boom")
    
    response = client.get("/test-generic-exc")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"

def test_docs_endpoints(client):
    # Swagger
    with patch("app.main.get_swagger_ui_html") as mock_swagger:
        mock_swagger.return_value = MagicMock()
        mock_swagger.return_value.body = b"<html></html>"
        response = client.get("/docs")
        assert response.status_code == 200
    
    # Redoc
    with patch("app.main.get_redoc_html") as mock_redoc:
        mock_redoc.return_value = MagicMock()
        mock_redoc.return_value.body = b"<html></html>"
        response = client.get("/redoc")
        assert response.status_code == 200
