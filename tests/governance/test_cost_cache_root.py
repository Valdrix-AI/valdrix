"""
Tests for Cost Cache - Redis/In-Memory Caching

Tests:
1. InMemoryCache backend
2. CostCache high-level API
3. Cache key generation
4. Cache invalidation
"""

import pytest
from unittest.mock import patch
from datetime import date

from app.shared.adapters.cost_cache import (
    InMemoryCache,
    CostCache,
    get_cost_cache,
)


class TestInMemoryCache:
    """Test InMemoryCache backend."""
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Getting non-existent key should return None."""
        cache = InMemoryCache()
        result = await cache.get("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Set then get should return value."""
        cache = InMemoryCache()
        await cache.set("test_key", '{"data": "value"}', ttl_seconds=3600)
        result = await cache.get("test_key")
        assert result == '{"data": "value"}'
    
    @pytest.mark.asyncio
    async def test_delete_key(self):
        """Delete should remove key."""
        cache = InMemoryCache()
        await cache.set("delete_me", "value", ttl_seconds=3600)
        await cache.delete("delete_me")
        result = await cache.get("delete_me")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_pattern(self):
        """Should delete keys matching pattern."""
        cache = InMemoryCache()
        await cache.set("tenant:123:costs", "data1", ttl_seconds=3600)
        await cache.set("tenant:123:carbon", "data2", ttl_seconds=3600)
        await cache.set("tenant:456:costs", "data3", ttl_seconds=3600)
        
        deleted = await cache.delete_pattern("tenant:123:*")
        
        assert deleted == 2
        assert await cache.get("tenant:123:costs") is None
        assert await cache.get("tenant:456:costs") is not None
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Health check should return True for in-memory."""
        cache = InMemoryCache()
        result = await cache.health_check()
        assert result is True


class TestCostCache:
    """Test CostCache high-level API."""
    
    @pytest.fixture
    def cache(self):
        """Create CostCache with in-memory backend."""
        backend = InMemoryCache()
        return CostCache(backend)
    
    @pytest.mark.asyncio
    async def test_get_daily_costs_miss(self, cache):
        """Cache miss should return None."""
        result = await cache.get_daily_costs(
            "tenant-123",
            date(2026, 1, 1),
            date(2026, 1, 31)
        )
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_and_get_daily_costs(self, cache):
        """Should cache and retrieve daily costs."""
        costs = [{"date": "2026-01-01", "amount": 100.0}]
        
        await cache.set_daily_costs(
            "tenant-123",
            date(2026, 1, 1),
            date(2026, 1, 31),
            costs
        )
        
        result = await cache.get_daily_costs(
            "tenant-123",
            date(2026, 1, 1),
            date(2026, 1, 31)
        )
        
        assert result == costs
    
    @pytest.mark.asyncio
    async def test_zombie_scan_caching(self, cache):
        """Should cache and retrieve zombie scans."""
        zombies = {"count": 5, "resources": []}
        
        await cache.set_zombie_scan("tenant-123", "us-east-1", zombies)
        
        result = await cache.get_zombie_scan("tenant-123", "us-east-1")
        assert result == zombies
    
    @pytest.mark.asyncio
    async def test_analysis_caching(self, cache):
        """Should cache and retrieve LLM analysis."""
        analysis = {"summary": "Test analysis"}
        
        await cache.set_analysis("tenant-123", "hash123", analysis)
        
        result = await cache.get_analysis("tenant-123", "hash123")
        assert result == analysis
    
    @pytest.mark.asyncio
    async def test_health_check_returns_dict(self, cache):
        """Health check should return status dict."""
        result = await cache.health_check()
        
        assert "healthy" in result
        assert "backend" in result
        assert result["backend"] == "memory"


class TestCostCacheKeyGeneration:
    """Test cache key generation."""
    
    def test_key_is_deterministic(self):
        """Same inputs should generate same key."""
        backend = InMemoryCache()
        cache = CostCache(backend)
        
        key1 = cache._generate_key("costs", "tenant", "2026-01")
        key2 = cache._generate_key("costs", "tenant", "2026-01")
        
        assert key1 == key2
    
    def test_different_inputs_different_keys(self):
        """Different inputs should generate different keys."""
        backend = InMemoryCache()
        cache = CostCache(backend)
        
        key1 = cache._generate_key("costs", "tenant1", "2026-01")
        key2 = cache._generate_key("costs", "tenant2", "2026-01")
        
        assert key1 != key2
    
    def test_key_starts_with_prefix(self):
        """Keys should start with valdrix prefix."""
        backend = InMemoryCache()
        cache = CostCache(backend)
        
        key = cache._generate_key("costs", "tenant", "period")
        
        assert key.startswith("valdrix:")


class TestCostCacheFactory:
    """Test get_cost_cache factory."""
    
    @pytest.mark.asyncio
    async def test_factory_returns_cache(self):
        """Factory should return CostCache instance."""
        with patch("app.shared.adapters.cost_cache.settings") as mock_settings:
            mock_settings.REDIS_URL = None
            
            # Reset singleton
            import app.shared.adapters.cost_cache as cache_module
            cache_module._cache_instance = None
            
            cache = await get_cost_cache()
            assert isinstance(cache, CostCache)
