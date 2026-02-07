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
        with patch.object(health_service, 'check_database', return_value=(True, {"latency_ms": 10.5})):
            with patch.object(health_service, 'check_redis', return_value=(True, {"latency_ms": 5.2})):
                with patch.object(health_service, 'check_aws', return_value=(False, {"error": "AWS unreachable"})):
                    
                    result = await health_service.check_all()
                    
                    assert result["status"] == "degraded"
                    assert result["database"]["status"] == "up"
                    assert result["redis"]["status"] == "up"
                    assert result["aws"]["status"] == "down"

    @pytest.mark.asyncio
    async def test_check_all_redis_degraded_only(self, health_service, mock_db):
        """Test overall health check when only Redis is degraded (lines 25-26)."""
        with patch.object(health_service, 'check_database', return_value=(True, {"latency_ms": 10.5})):
            with patch.object(health_service, 'check_redis', return_value=(False, {"error": "Redis down"})):
                with patch.object(health_service, 'check_aws', return_value=(True, {"reachable": True})):
                    
                    result = await health_service.check_all()
                    
                    assert result["status"] == "degraded"
                    assert result["database"]["status"] == "up"
                    assert result["redis"]["status"] == "down"
                    assert result["aws"]["status"] == "up"

    @pytest.mark.asyncio
    async def test_check_aws_client_error(self, health_service):
        """Test AWS health check with client error (4xx) - lines 74."""
        mock_response = MagicMock()
        mock_response.status_code = 404  # Client error but still "reachable"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            success, details = await health_service.check_aws()
            
            assert success is True
            assert details["reachable"] is True

    @pytest.mark.asyncio
    async def test_check_aws_redirect_status(self, health_service):
        """Test AWS health check with redirect status (3xx) - lines 74."""
        mock_response = MagicMock()
        mock_response.status_code = 301  # Redirect but still "reachable"
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            success, details = await health_service.check_aws()
            
            assert success is True
            assert details["reachable"] is True
