import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.core.cache import CacheService, QueryCache


@pytest.mark.asyncio
async def test_delete_pattern_no_keys():
    async def empty_scan_iter(match=None):
        if False:
            yield match  # pragma: no cover

    mock_redis = AsyncMock()
    mock_redis.scan_iter = MagicMock(side_effect=empty_scan_iter)

    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        service = CacheService()
        result = await service.delete_pattern("missing:*")

    assert result is True
    mock_redis.delete.assert_not_called()


def test_get_sync_client_returns_none_without_config():
    with patch("app.shared.core.cache.get_settings") as mock_settings:
        mock_settings.return_value.UPSTASH_REDIS_URL = None
        mock_settings.return_value.UPSTASH_REDIS_TOKEN = None
        from app.shared.core.cache import _get_sync_client
        assert _get_sync_client() is None


@pytest.mark.asyncio
async def test_cached_query_tenant_aware_false_does_not_use_tenant():
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(db, tenant_id, extra=None):
        return {"ok": True, "extra": extra}

    with patch.object(cache, "_make_cache_key", wraps=cache._make_cache_key) as mock_key:
        wrapped = cache.cached_query(tenant_aware=False)(handler)
        await wrapped("db", "tenant-1", extra="x")

    _, kwargs = mock_key.call_args
    assert kwargs["tenant_id"] is None
