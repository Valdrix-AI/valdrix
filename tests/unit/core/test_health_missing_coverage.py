"""
Targeted tests for app/shared/core/health.py missing coverage lines
"""

import pytest
import pytest_asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.health import HealthService


class TestHealthServiceMissingCoverage:
    """Test health check service missing coverage lines."""

    @pytest_asyncio.fixture
    async def mock_db(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest_asyncio.fixture
    async def health_service(self, mock_db):
        """Create health service instance."""
        return HealthService(mock_db)

    @pytest.mark.asyncio
    async def test_check_all_aws_degraded_only(self, health_service, mock_db):
        """Test overall health check when only AWS is degraded (lines 25-26)."""
        with (
            patch.object(
                health_service,
                "_check_database",
                return_value={"status": "up", "latency_ms": 10.5},
            ),
            patch.object(
                health_service,
                "_check_cache",
                return_value={"status": "healthy", "latency_ms": 5.2},
            ),
            patch.object(
                health_service,
                "_check_external_services",
                return_value={
                    "status": "degraded",
                    "services": {"aws_sts": {"status": "unhealthy"}},
                },
            ),
            patch.object(
                health_service,
                "_check_circuit_breakers",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_system_resources",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_background_jobs",
                return_value={"status": "healthy"},
            ),
        ):
            result = await health_service.check_all()

            assert result["status"] == "degraded"
            assert result["database"]["status"] == "up"
            assert result["redis"]["status"] == "healthy"
            assert result["aws"]["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_check_all_redis_degraded_only(self, health_service, mock_db):
        """Test overall health check when only Redis is degraded (lines 25-26)."""
        with (
            patch.object(
                health_service,
                "_check_database",
                return_value={"status": "up", "latency_ms": 10.5},
            ),
            patch.object(
                health_service,
                "_check_cache",
                return_value={"status": "degraded", "message": "Redis down"},
            ),
            patch.object(
                health_service,
                "_check_external_services",
                return_value={
                    "status": "healthy",
                    "services": {"aws_sts": {"status": "healthy"}},
                },
            ),
            patch.object(
                health_service,
                "_check_circuit_breakers",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_system_resources",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_background_jobs",
                return_value={"status": "healthy"},
            ),
        ):
            result = await health_service.check_all()

            assert result["status"] == "degraded"
            assert result["database"]["status"] == "up"
            assert result["redis"]["status"] == "degraded"
            assert result["aws"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_aws_client_error(self, health_service):
        """Test AWS health check with client error (4xx) - lines 74."""
        mock_response = MagicMock()
        mock_response.status_code = 404  # Client error but still "reachable"

        with patch("app.shared.core.health.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            success, details = await health_service.check_aws()

            assert success is True
            assert details["reachable"] is True

    @pytest.mark.asyncio
    async def test_check_aws_redirect_status(self, health_service):
        """Test AWS health check with redirect status (3xx) - lines 74."""
        mock_response = MagicMock()
        mock_response.status_code = 301  # Redirect but still "reachable"

        with patch("app.shared.core.health.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            success, details = await health_service.check_aws()

            assert success is True
            assert details["reachable"] is True

    @pytest.mark.asyncio
    async def test_check_all_unhealthy_db_down(self, health_service):
        """Test overall health check when database is down (line 24)."""
        with (
            patch.object(
                health_service,
                "_check_database",
                return_value={"status": "down", "error": "Connection failed"},
            ),
            patch.object(
                health_service,
                "_check_cache",
                return_value={"status": "healthy", "latency_ms": 5.2},
            ),
            patch.object(
                health_service,
                "_check_external_services",
                return_value={
                    "status": "healthy",
                    "services": {"aws_sts": {"status": "healthy"}},
                },
            ),
            patch.object(
                health_service,
                "_check_circuit_breakers",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_system_resources",
                return_value={"status": "healthy"},
            ),
            patch.object(
                health_service,
                "_check_background_jobs",
                return_value={"status": "healthy"},
            ),
        ):
            result = await health_service.check_all()

            assert result["status"] == "unhealthy"
            assert result["database"]["status"] == "down"

    @pytest.mark.asyncio
    async def test_check_database_exception(self, health_service, mock_db):
        """Test database check handling exception (lines 43-45)."""
        with patch(
            "app.shared.core.health.db_health_check", side_effect=Exception("DB error")
        ):
            success, details = await health_service.check_database()

            assert success is False
            assert "DB error" in details["error"]

    @pytest.mark.asyncio
    async def test_check_redis_not_configured(self, health_service):
        """Test redis check when not configured (lines 49-50)."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = None
        with patch("app.shared.core.health.get_settings", return_value=mock_settings):
            success, details = await health_service.check_redis()

        assert success is True
        assert details["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_check_redis_client_missing(self, health_service):
        """Test redis check when client is missing (lines 55-56)."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://host"
        with (
            patch("app.shared.core.health.get_settings", return_value=mock_settings),
            patch("app.shared.core.rate_limit.get_redis_client", return_value=None),
        ):
            success, details = await health_service.check_redis()

        assert success is False
        assert "not available" in details["error"]

    @pytest.mark.asyncio
    async def test_check_redis_exception(self, health_service):
        """Test redis check exception (lines 63-65)."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://host"
        with (
            patch("app.shared.core.health.get_settings", return_value=mock_settings),
            patch("app.shared.core.rate_limit.get_redis_client") as mock_get_client,
        ):
            mock_client = MagicMock()
            mock_client.ping = AsyncMock(side_effect=Exception("Redis error"))
            mock_get_client.return_value = mock_client

            success, details = await health_service.check_redis()

        assert success is False
        assert "Redis error" in details["error"]

    @pytest.mark.asyncio
    async def test_check_database_success(self, health_service, mock_db):
        """Test database check success (lines 41-42)."""
        with patch(
            "app.shared.core.health.db_health_check",
            return_value={"status": "up", "latency_ms": 1.0},
        ):
            success, details = await health_service.check_database()

        assert success is True
        assert "latency_ms" in details

    @pytest.mark.asyncio
    async def test_check_redis_success(self, health_service):
        """Test redis check success (lines 62)."""
        mock_settings = MagicMock()
        mock_settings.REDIS_URL = "redis://host"
        with (
            patch("app.shared.core.health.get_settings", return_value=mock_settings),
            patch("app.shared.core.rate_limit.get_redis_client") as mock_get_client,
        ):
            mock_client = MagicMock()
            mock_client.ping = AsyncMock()
            mock_get_client.return_value = mock_client

            success, details = await health_service.check_redis()

        assert success is True
        assert "latency_ms" in details

    @pytest.mark.asyncio
    async def test_check_all_healthy(self, health_service):
        """Test overall health check when all services are healthy (line 22)."""
        with patch.object(
            health_service,
            "_check_database",
            return_value={"status": "up", "latency_ms": 10.5},
        ):
            with patch.object(
                health_service,
                "_check_cache",
                return_value={"status": "healthy", "latency_ms": 5.2},
            ):
                with patch.object(
                    health_service,
                    "_check_external_services",
                    return_value={
                        "status": "healthy",
                        "services": {"aws_sts": {"status": "healthy"}},
                    },
                ):
                    with patch.object(
                        health_service,
                        "_check_circuit_breakers",
                        return_value={"status": "healthy"},
                    ):
                        with patch.object(
                            health_service,
                            "_check_system_resources",
                            return_value={"status": "healthy"},
                        ):
                            with patch.object(
                                health_service,
                                "_check_background_jobs",
                                return_value={"status": "healthy"},
                            ):
                                result = await health_service.check_all()
                                assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_aws_server_error(self, health_service):
        """Test AWS health check with server error (line 76)."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.shared.core.health.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            success, details = await health_service.check_aws()

            assert success is False
            assert "STS returned 500" in details["error"]

    @pytest.mark.asyncio
    async def test_check_aws_exception(self, health_service):
        """Test AWS health check exception (lines 78-79)."""
        with patch("app.shared.core.health.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Network fail")
            )

            success, details = await health_service.check_aws()

            print(f"success: {success}, details: {details}")

            assert success is False
            assert "Network fail" in details["error"]
