"""
Tests for CacheService with Upstash Redis

Tests behavior when:
1. Redis is not configured (graceful fallback)
2. Redis is configured (mocked operations)
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import json

from app.shared.cache import CacheService, get_cache_service


class TestCacheServiceDisabled:
    """Tests for cache service when Redis is not configured."""
    
    def test_disabled_when_no_credentials(self):
        """Cache is disabled when UPSTASH credentials are missing."""
        with patch('app.shared.cache.get_settings') as mock_settings:
            mock_settings.return_value.UPSTASH_REDIS_URL = None
            mock_settings.return_value.UPSTASH_REDIS_TOKEN = None
            
            # Reset singleton
            import app.shared.cache as cache_module
            cache_module._async_client = None
            cache_module._cache_service = None
            
            service = CacheService()
            assert service.enabled is False
    
    @pytest.mark.asyncio
    async def test_get_analysis_returns_none_when_disabled(self):
        """get_analysis returns None when cache is disabled."""
        with patch('app.shared.cache.get_settings') as mock_settings:
            mock_settings.return_value.UPSTASH_REDIS_URL = None
            mock_settings.return_value.UPSTASH_REDIS_TOKEN = None
            
            import app.shared.cache as cache_module
            cache_module._async_client = None
            cache_module._cache_service = None
            
            service = CacheService()
            result = await service.get_analysis(uuid4())
            assert result is None
    
    @pytest.mark.asyncio
    async def test_set_analysis_returns_false_when_disabled(self):
        """set_analysis returns False when cache is disabled."""
        with patch('app.shared.cache.get_settings') as mock_settings:
            mock_settings.return_value.UPSTASH_REDIS_URL = None
            mock_settings.return_value.UPSTASH_REDIS_TOKEN = None
            
            import app.shared.cache as cache_module
            cache_module._async_client = None
            cache_module._cache_service = None
            
            service = CacheService()
            result = await service.set_analysis(uuid4(), {"test": "data"})
            assert result is False


class TestCacheServiceEnabled:
    """Tests for cache service when Redis is configured (mocked)."""
    
    @pytest.mark.asyncio
    async def test_get_analysis_returns_cached_data(self):
        """get_analysis returns parsed JSON when data exists."""
        tenant_id = uuid4()
        cached_data = {"anomalies": [], "recommendations": []}
        
        with patch('app.shared.cache.get_settings') as mock_settings, \
             patch('app.shared.cache.AsyncRedis') as MockRedis:
            mock_settings.return_value.UPSTASH_REDIS_URL = "https://test.upstash.io"
            mock_settings.return_value.UPSTASH_REDIS_TOKEN = "test_token"
            
            # Setup mock Redis client
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=json.dumps(cached_data))
            MockRedis.return_value = mock_client
            
            import app.shared.cache as cache_module
            cache_module._async_client = None
            cache_module._cache_service = None
            
            service = CacheService()
            service.client = mock_client
            service.enabled = True
            
            result = await service.get_analysis(tenant_id)
            assert result == cached_data
            mock_client.get.assert_called_once_with(f"analysis:{tenant_id}")
    
    @pytest.mark.asyncio
    async def test_set_analysis_stores_data_with_ttl(self):
        """set_analysis stores JSON with 24h TTL."""
        tenant_id = uuid4()
        analysis_data = {"anomalies": [], "summary": {"total_estimated_savings": "$0/month"}}
        
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(return_value=True)
        
        service = CacheService()
        service.client = mock_client
        service.enabled = True
        
        result = await service.set_analysis(tenant_id, analysis_data)
        
        assert result is True
        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0] == f"analysis:{tenant_id}"
        assert json.loads(call_args[0][1]) == analysis_data
        assert call_args[1]["ex"] == 86400  # 24 hours in seconds
    
    @pytest.mark.asyncio
    async def test_get_analysis_handles_errors_gracefully(self):
        """get_analysis returns None on Redis errors."""
        tenant_id = uuid4()
        
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection failed"))
        
        service = CacheService()
        service.client = mock_client
        service.enabled = True
        
        result = await service.get_analysis(tenant_id)
        assert result is None  # Graceful fallback on error


class TestCacheServiceSingleton:
    """Tests for singleton behavior."""
    
    def test_get_cache_service_returns_same_instance(self):
        """get_cache_service returns the same instance."""
        with patch('app.shared.cache.get_settings') as mock_settings:
            mock_settings.return_value.UPSTASH_REDIS_URL = None
            mock_settings.return_value.UPSTASH_REDIS_TOKEN = None
            
            import app.shared.cache as cache_module
            cache_module._cache_service = None
            
            service1 = get_cache_service()
            service2 = get_cache_service()
            
            assert service1 is service2
