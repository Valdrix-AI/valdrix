import json
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from app.shared.core.cache import QueryCache


@pytest.mark.asyncio
async def test_make_cache_key_includes_tenant_prefix():
    cache = QueryCache(redis_client=AsyncMock())
    key = cache._make_cache_key("query_fn", {"a": 1}, tenant_id="t-1")
    assert key.startswith("query_cache:tenant:t-1:")


def test_make_cache_key_deterministic():
    cache = QueryCache(redis_client=AsyncMock())
    key1 = cache._make_cache_key("query_fn", {"a": 1, "b": 2}, tenant_id="t-1")
    key2 = cache._make_cache_key("query_fn", {"b": 2, "a": 1}, tenant_id="t-1")
    assert key1 == key2


@pytest.mark.asyncio
async def test_cached_query_returns_cached_result():
    redis = AsyncMock()
    cached = {"ok": True}
    redis.get.return_value = json.dumps(cached)
    cache = QueryCache(redis_client=redis)

    async def handler(db, tenant_id):
        return {"ok": False}

    wrapped = cache.cached_query()(handler)
    result = await wrapped("db", "tenant-1")

    assert result == cached


@pytest.mark.asyncio
async def test_cached_query_sets_on_miss():
    redis = AsyncMock()
    redis.get.return_value = None
    cache = QueryCache(redis_client=redis, default_ttl=123)

    async def handler(db, tenant_id, extra=None):
        return {"value": 42, "extra": extra}

    wrapped = cache.cached_query()(handler)
    result = await wrapped("db", "tenant-1", extra="x")

    assert result == {"value": 42, "extra": "x"}
    redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_get_cached_result_invalid_json_returns_none():
    redis = AsyncMock()
    redis.get.return_value = "{broken"
    cache = QueryCache(redis_client=redis)
    assert await cache.get_cached_result("bad-key") is None


@pytest.mark.asyncio
async def test_invalidate_tenant_cache_scans_and_deletes():
    redis = AsyncMock()
    redis.scan = AsyncMock(side_effect=[(1, ["k1", "k2"]), (0, ["k3"])])
    cache = QueryCache(redis_client=redis)

    await cache.invalidate_tenant_cache("tenant-1")

    redis.scan.assert_awaited()
    redis.delete.assert_any_await("k1", "k2")
    redis.delete.assert_any_await("k3")


@pytest.mark.asyncio
async def test_cached_query_waits_for_locked_result_and_avoids_duplicate_execution():
    redis = AsyncMock()
    cached = {"ok": True}
    # 1st get: initial cache miss
    # 2nd get: still missing while waiting on lock owner
    # 3rd get: lock owner has populated cache
    redis.get = AsyncMock(side_effect=[None, None, json.dumps(cached)])
    redis.set = AsyncMock(return_value=False)  # lock acquisition denied
    cache = QueryCache(redis_client=redis)

    handler = AsyncMock(return_value={"ok": False})
    wrapped = cache.cached_query()(handler)

    with patch(
        "app.shared.core.cache.asyncio.sleep", new=AsyncMock(return_value=None)
    ):
        result = await wrapped("db", "tenant-1")

    assert result == cached
    handler.assert_not_awaited()
    # Should not release lock it never acquired.
    redis.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_cached_query_does_not_release_foreign_lock_on_timeout_fallback():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)

    async def set_side_effect(*args, **kwargs):
        # Lock acquisition and re-acquisition attempts fail.
        if kwargs.get("nx"):
            return False
        # Cache set (non-lock write) succeeds.
        return True

    redis.set = AsyncMock(side_effect=set_side_effect)
    cache = QueryCache(redis_client=redis)

    handler = AsyncMock(return_value={"value": 7})
    wrapped = cache.cached_query()(handler)

    with patch(
        "app.shared.core.cache.asyncio.sleep", new=AsyncMock(return_value=None)
    ):
        result = await wrapped("db", "tenant-1")

    assert result == {"value": 7}
    handler.assert_awaited_once()
    # Critical: lock release must happen only when lock is owned.
    redis.delete.assert_not_awaited()
