from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.shared.core.cache import CacheService, QueryCache, _get_async_client


@pytest.mark.asyncio
async def test_delete_pattern_scan_fallback_path() -> None:
    client = AsyncMock()
    client.scan_iter = None
    client.scan = AsyncMock(side_effect=[("1", ["k1"]), ("0", ["k2"])])
    with patch("app.shared.core.cache._get_async_client", return_value=client):
        service = CacheService()
        deleted = await service.delete_pattern("prefix:*")
    assert deleted is True
    client.delete.assert_any_await("k1")
    client.delete.assert_any_await("k2")


@pytest.mark.asyncio
async def test_cache_get_handles_bad_bytes_and_unexpected_type() -> None:
    client = AsyncMock()
    with patch("app.shared.core.cache._get_async_client", return_value=client):
        service = CacheService()

    client.get.return_value = b"\xff"
    assert await service.get("bad-bytes") is None

    client.get.return_value = object()
    assert await service.get("bad-type") is None


@pytest.mark.asyncio
async def test_query_cache_disabled_decorator_passthrough() -> None:
    cache = QueryCache(redis_client=None)

    async def handler(_db: object, tenant_id: str) -> dict[str, str]:
        return {"tenant": tenant_id}

    wrapped = cache.cached_query(ttl=30)(handler)
    result = await wrapped(object(), "tenant-1")
    assert result == {"tenant": "tenant-1"}


@pytest.mark.asyncio
async def test_query_cache_set_cached_result_noop_when_disabled() -> None:
    cache = QueryCache(redis_client=None)
    await cache.set_cached_result("key", {"value": 1}, ttl=10)
    await cache.invalidate_tenant_cache("tenant-1")


def test_get_async_client_returns_none_without_config() -> None:
    with patch("app.shared.core.cache.get_settings") as get_settings, patch(
        "app.shared.core.cache._async_client", new=None
    ):
        get_settings.return_value.UPSTASH_REDIS_URL = None
        get_settings.return_value.UPSTASH_REDIS_TOKEN = None
        assert _get_async_client() is None


def test_get_async_client_singleton_creation() -> None:
    with patch("app.shared.core.cache.get_settings") as get_settings, patch(
        "app.shared.core.cache._async_client", new=None
    ), patch("app.shared.core.cache.AsyncRedis") as async_redis_cls:
        get_settings.return_value.UPSTASH_REDIS_URL = "redis://example"
        get_settings.return_value.UPSTASH_REDIS_TOKEN = "token"
        c1 = _get_async_client()
        c2 = _get_async_client()
    assert c1 is not None
    assert c1 is c2
    async_redis_cls.assert_called_once()


@pytest.mark.asyncio
async def test_cache_set_uses_default_ttl_path() -> None:
    client = AsyncMock()
    with patch("app.shared.core.cache._get_async_client", return_value=client):
        service = CacheService()
        assert await service.set("k", {"a": 1}, ttl=timedelta(seconds=30)) is True
