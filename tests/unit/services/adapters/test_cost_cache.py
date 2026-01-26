"""
Tests for CostCache - Caching logic for cost data
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, timezone, timedelta
from app.shared.adapters.cost_cache import (
    InMemoryCache,
    RedisCache,
    CostCache,
    get_cost_cache,
    CacheBackend
)


class TestInMemoryCache:
    @pytest.mark.asyncio
    async def test_set_get(self):
        cache = InMemoryCache()
        await cache.set("key", "value", 10)
        assert await cache.get("key") == "value"

    @pytest.mark.asyncio
    async def test_get_expired(self):
        cache = InMemoryCache()
        with patch("app.shared.adapters.cost_cache.datetime") as mock_dt:
            # mock_dt is the datetime module in cost_cache
            now = datetime.now(timezone.utc)
            mock_dt.now.return_value = now
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta
            
            await cache.set("key", "value", 10)
            
            # Move time forward
            mock_dt.now.return_value = now + timedelta(seconds=11)
            assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_delete(self):
        cache = InMemoryCache()
        await cache.set("key", "value", 10)
        await cache.delete("key")
        assert await cache.get("key") is None

    @pytest.mark.asyncio
    async def test_delete_pattern(self):
        cache = InMemoryCache()
        await cache.set("tenant:1:a", "v1", 10)
        await cache.set("tenant:1:b", "v2", 10)
        await cache.set("tenant:2:a", "v3", 10)
        
        count = await cache.delete_pattern("tenant:1:*")
        assert count == 2
        assert await cache.get("tenant:1:a") is None
        assert await cache.get("tenant:2:a") == "v3"


class TestRedisCache:
    @patch("redis.asyncio.from_url")
    @pytest.mark.asyncio
    async def test_set_get(self, mock_from_url):
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.get.return_value = "value"
        
        cache = RedisCache(redis_url="redis://localhost")
        with patch.object(cache, "_get_client", return_value=mock_redis):
            await cache.set("key", "value", 10)
            val = await cache.get("key")
            
            assert val == "value"
            mock_redis.setex.assert_called_once()
            mock_redis.get.assert_called_once_with("key")

    @patch("redis.asyncio.from_url")
    @pytest.mark.asyncio
    async def test_delete_pattern(self, mock_from_url):
        mock_redis = AsyncMock()
        mock_from_url.return_value = mock_redis
        mock_redis.scan.side_effect = [(0, ["k1", "k2"])] # Corrected scan return
        
        cache = RedisCache(redis_url="redis://localhost")
        with patch.object(cache, "_get_client", return_value=mock_redis):
            count = await cache.delete_pattern("val:*")
            
            assert count == 2
            mock_redis.delete.assert_called_once_with("k1", "k2")


class TestCostCache:
    @pytest.mark.asyncio
    async def test_get_set_daily_costs(self):
        backend = InMemoryCache()
        cache = CostCache(backend)
        tenant_id = "tenant-1"
        start = date(2026, 1, 1)
        end = date(2026, 1, 2)
        costs = [{"service": "EC2", "amount": 10.5}]
        
        await cache.set_daily_costs(tenant_id, start, end, costs)
        cached = await cache.get_daily_costs(tenant_id, start, end)
        
        assert cached == costs

    @pytest.mark.asyncio
    async def test_get_set_zombie_scan(self):
        backend = InMemoryCache()
        cache = CostCache(backend)
        tenant_id = "tenant-1"
        region = "us-east-1"
        zombies = {"summary": {"count": 5}}
        
        await cache.set_zombie_scan(tenant_id, region, zombies)
        cached = await cache.get_zombie_scan(tenant_id, region)
        
        assert cached == zombies

    @pytest.mark.asyncio
    async def test_invalidate_tenant(self):
        backend = MagicMock(spec=CacheBackend)
        backend.delete_pattern = AsyncMock(return_value=5)
        cache = CostCache(backend)
        
        await cache.invalidate_tenant("tenant-1")
        backend.delete_pattern.assert_called_once()


@pytest.mark.asyncio
async def test_get_cost_cache_factory():
    with patch("app.shared.adapters.cost_cache.settings") as mock_settings:
        mock_settings.REDIS_URL = None
        # Reset singleton for test
        with patch("app.shared.adapters.cost_cache._cache_instance", None):
            cache = await get_cost_cache()
            assert isinstance(cache.backend, InMemoryCache)
            
            mock_settings.REDIS_URL = "redis://localhost"
            with patch("app.shared.adapters.cost_cache.RedisCache") as mock_redis_cls:
                mock_redis = MagicMock(spec=RedisCache)
                mock_redis.health_check = AsyncMock(return_value=True)
                mock_redis_cls.return_value = mock_redis
                
                # Reset singleton again
                with patch("app.shared.adapters.cost_cache._cache_instance", None):
                    cache = await get_cost_cache()
                    assert cache.backend is mock_redis
