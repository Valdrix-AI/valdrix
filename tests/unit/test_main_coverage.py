import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def mock_lifespan_deps():
    mock_dispose = AsyncMock()

    class _EngineStub:
        async def dispose(self):
            await mock_dispose()

    with (
        patch("os.makedirs") as mock_makedirs,
        patch("app.main.EmissionsTracker") as mock_tracker,
        patch(
            "app.modules.governance.domain.scheduler.SchedulerService"
        ) as mock_scheduler,
        patch("app.main.get_engine", return_value=_EngineStub()),
    ):
        yield {
            "makedirs": mock_makedirs,
            "tracker": mock_tracker.return_value,
            "scheduler": mock_scheduler.return_value,
            "dispose": mock_dispose,
        }


@pytest.mark.asyncio
async def test_lifespan_flow(mock_lifespan_deps):
    """Test app lifespan setup and teardown."""
    from app.main import lifespan, app

    async with lifespan(app):
        mock_lifespan_deps["makedirs"].assert_called_with(
            "/tmp/valdrics",
            exist_ok=True,
        )

    mock_lifespan_deps["dispose"].assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_skips_scheduler_when_disabled(mock_lifespan_deps):
    from app.main import lifespan, app

    with patch("app.main.reload_settings_from_environment") as mock_reload:
        from app.main import settings as live_settings

        mock_reload.return_value = live_settings
        live_settings.TESTING = False
        live_settings.REDIS_URL = "redis://localhost:6379/0"
        live_settings.ENABLE_SCHEDULER = False

        async with lifespan(app):
            pass

    mock_lifespan_deps["scheduler"].start.assert_not_called()


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
        "aws": {"status": "up"},
    }
    with patch(
        "app.shared.core.health.HealthService.check_all", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = mock_health
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


def test_valdrics_exception_handler(client):
    from app.main import app
    from app.shared.core.exceptions import ValdricsException

    @app.get("/test-valdrics-exc")
    async def trigger_exc():
        raise ValdricsException(
            message="Test message", code="test_code", status_code=418
        )

    response = client.get("/test-valdrics-exc")
    assert response.status_code == 418
    assert response.json()["error"]["code"] == "test_code"


def test_generic_exception_handler(client):
    from app.main import app

    @app.get("/test-generic-exc")
    async def trigger_exc():
        raise Exception("Boom")

    response = client.get("/test-generic-exc")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"


def test_docs_endpoints(client):
    from app.main import settings as live_settings

    original_environment = live_settings.ENVIRONMENT
    original_docs_public = live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY
    live_settings.ENVIRONMENT = "development"
    live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY = False
    # Swagger
    try:
        with patch("app.main.render_swagger_ui_html") as mock_swagger:
            mock_swagger.return_value = MagicMock()
            mock_swagger.return_value.body = b"<html></html>"
            mock_swagger.return_value.status_code = 200
            response = client.get("/docs")
            assert response.status_code == 200

        # Redoc
        with patch("app.main.render_redoc_ui_html") as mock_redoc:
            mock_redoc.return_value = MagicMock()
            mock_redoc.return_value.body = b"<html></html>"
            mock_redoc.return_value.status_code = 200
            response = client.get("/redoc")
            assert response.status_code == 200
    finally:
        live_settings.ENVIRONMENT = original_environment
        live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY = original_docs_public


def test_docs_endpoints_blocked_in_strict_env(client):
    from app.main import settings as live_settings

    original_environment = live_settings.ENVIRONMENT
    original_docs_public = live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY
    original_testing = live_settings.TESTING
    live_settings.ENVIRONMENT = "production"
    live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY = False
    live_settings.TESTING = False
    try:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
    finally:
        live_settings.ENVIRONMENT = original_environment
        live_settings.EXPOSE_API_DOCUMENTATION_PUBLICLY = original_docs_public
        live_settings.TESTING = original_testing
