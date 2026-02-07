import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.core.cache import CacheService, get_cache_service

@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis

@pytest.mark.asyncio
async def test_cache_get_set(mock_redis):
    """Test basic get/set operations."""
    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        service = CacheService()
        
        # Test Set
        await service.set("test-key", {"foo": "bar"}, ttl=60)
        mock_redis.set.assert_called_with(
            "test-key", 
            json.dumps({"foo": "bar"}), 
            ex=60
        )
        
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
    # Mock scan_iter to return keys
    mock_redis.scan_iter = MagicMock(return_value=iter(["key1", "key2"]))
    
    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        service = CacheService()
        await service.delete_pattern("prefix:*")
    
    mock_redis.delete.assert_called()
    # Check that delete was called with the keys found
    call_args = mock_redis.delete.call_args[0]
    assert "key1" in call_args
    assert "key2" in call_args

def test_singleton_getter():
    """Test get_cache_service singleton."""
    with patch("app.shared.core.cache.Redis", new=MagicMock()):
        s1 = get_cache_service()
        s2 = get_cache_service()
        assert s1 is s2
