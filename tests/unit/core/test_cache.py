import pytest
from typing import Dict
import json
from datetime import timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from app.shared.core.cache import get_cache_service


@pytest.fixture(autouse=True)
def reset_cache_singleton():
    """Reset the global cache service singleton before each test."""
    import app.shared.core.cache as cache_mod

    cache_mod._cache_service = None
    cache_mod._async_client = None
    # Patch get_settings globally to ensure enabled=True
    with patch("app.shared.core.cache.get_settings") as mock_settings:
        mock_settings.return_value.UPSTASH_REDIS_URL = "redis://test:6379"
        mock_settings.return_value.UPSTASH_REDIS_TOKEN = "test-token"
        yield


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.mark.asyncio
async def test_cache_get_set(mock_redis):
    """Test basic get/set operations."""
    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        from app.shared.core.cache import CacheService

        service = CacheService()

        # Test Set
        await service.set("test-key", {"foo": "bar"}, ttl=timedelta(seconds=60))
        mock_redis.set.assert_called()  # Check call

        # Test Get Hit
        mock_redis.get.return_value = json.dumps({"foo": "bar"})
        val = await service.get("test-key")
        assert val == {"foo": "bar"}

        # Test Get Miss
        mock_redis.get.return_value = None
        val = await service.get("missing")
        assert val is None


@pytest.mark.asyncio
async def test_cache_delete_pattern(mock_redis):
    """Test deleting by pattern."""

    # Properly mock scan_iter as an async iterator
    async def mock_scan_iter(match=None):
        for k in ["key1", "key2"]:
            yield k

    mock_redis.scan_iter = MagicMock(side_effect=mock_scan_iter)

    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        from app.shared.core.cache import CacheService

        service = CacheService()
        await service.delete_pattern("prefix:*")

    mock_redis.delete.assert_called_with("key1", "key2")


def test_singleton_getter():
    """Test get_cache_service singleton."""
    with patch("app.shared.core.cache._get_async_client", return_value=AsyncMock()):
        s1 = get_cache_service()
        s2 = get_cache_service()
        assert s1 is s2
