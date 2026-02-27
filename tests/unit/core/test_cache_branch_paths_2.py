from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.shared.core.cache import CacheService, QueryCache, _get_sync_client


class _BytesDecodeNone(bytes):
    def decode(self, *_args: object, **_kwargs: object) -> None:  # type: ignore[override]
        return None


@pytest.fixture(autouse=True)
def _reset_cache_singletons() -> None:
    import app.shared.core.cache as cache_mod

    cache_mod._sync_client = None
    cache_mod._async_client = None
    cache_mod._cache_service = None


@pytest.mark.asyncio
async def test_cache_cost_wrappers_delegate_to_internal_methods() -> None:
    with patch("app.shared.core.cache._get_async_client", return_value=AsyncMock()):
        service = CacheService()

    tenant_id = uuid4()
    with (
        patch.object(service, "_get", new=AsyncMock(return_value=[{"ok": True}])) as mock_get,
        patch.object(service, "_set", new=AsyncMock(return_value=True)) as mock_set,
    ):
        assert await service.get_cost_data(tenant_id, "7d") == [{"ok": True}]
        assert await service.set_cost_data(tenant_id, "7d", [{"c": 1}]) is True

    mock_get.assert_awaited_once_with(f"costs:{tenant_id}:7d")
    mock_set.assert_awaited_once()
    assert mock_set.call_args.args[0] == f"costs:{tenant_id}:7d"


@pytest.mark.asyncio
async def test_cache_invalidate_tenant_disabled_and_exception_paths() -> None:
    with patch("app.shared.core.cache._get_async_client", return_value=None):
        disabled = CacheService()
    assert await disabled.invalidate_tenant(uuid4()) is False

    client = AsyncMock()
    client.delete.side_effect = RuntimeError("boom")
    with patch("app.shared.core.cache._get_async_client", return_value=client):
        service = CacheService()
    assert await service.invalidate_tenant(uuid4()) is False


@pytest.mark.asyncio
async def test_cache_delete_pattern_disabled_fallback_empty_and_error_paths() -> None:
    with patch("app.shared.core.cache._get_async_client", return_value=None):
        service_disabled = CacheService()
    assert await service_disabled.delete_pattern("a:*") is False

    client_empty = AsyncMock()
    client_empty.scan_iter = None
    client_empty.scan = AsyncMock(side_effect=[("1", []), ("0", [])])
    with patch("app.shared.core.cache._get_async_client", return_value=client_empty):
        service_empty = CacheService()
    assert await service_empty.delete_pattern("a:*") is True
    client_empty.delete.assert_not_called()

    client_error = AsyncMock()
    client_error.scan_iter = None
    client_error.scan = AsyncMock(side_effect=RuntimeError("scan failed"))
    with patch("app.shared.core.cache._get_async_client", return_value=client_error):
        service_error = CacheService()
    assert await service_error.delete_pattern("a:*") is False


@pytest.mark.asyncio
async def test_cache_get_handles_primitive_and_bytes_decode_to_none() -> None:
    client = AsyncMock()
    with patch("app.shared.core.cache._get_async_client", return_value=client):
        service = CacheService()

    client.get.return_value = 7
    assert await service.get("k:int") == 7

    client.get.return_value = _BytesDecodeNone(b"ignored")
    assert await service.get("k:none-after-decode") is None


def test_get_sync_client_reuses_existing_singleton() -> None:
    existing = object()
    with (
        patch("app.shared.core.cache._sync_client", new=existing),
        patch("app.shared.core.cache.get_settings") as mock_settings,
        patch("app.shared.core.cache.Redis") as mock_redis_cls,
    ):
        mock_settings.return_value = SimpleNamespace(
            UPSTASH_REDIS_URL="redis://example",
            UPSTASH_REDIS_TOKEN="token",
        )
        assert _get_sync_client() is existing
    mock_redis_cls.assert_not_called()


def test_query_cache_make_cache_key_includes_tenant_prefix() -> None:
    cache = QueryCache(redis_client=AsyncMock())
    key = cache._make_cache_key("q", {"a": 1}, tenant_id="tenant-1")
    assert key.startswith("query_cache:tenant:tenant-1:")


@pytest.mark.asyncio
async def test_query_cache_get_cached_result_disabled_and_branch_paths() -> None:
    disabled = QueryCache(redis_client=None)
    assert await disabled.get_cached_result("k") is None

    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    redis.get.return_value = b"\xff"
    assert await cache.get_cached_result("k1") is None

    redis.get.return_value = '[1, 2]'
    assert await cache.get_cached_result("k2") == [1, 2]

    redis.get.return_value = True
    assert await cache.get_cached_result("k3") is True

    redis.get.return_value = None
    assert await cache.get_cached_result("k4") is None

    redis.get.side_effect = RuntimeError("get failed")
    assert await cache.get_cached_result("k5") is None


@pytest.mark.asyncio
async def test_query_cache_set_cached_result_error_and_invalidate_tenant_cache_paths() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    redis.set.side_effect = RuntimeError("set failed")
    await cache.set_cached_result("k", {"a": 1})

    redis.set.side_effect = None
    redis.scan.side_effect = [(1, ["k1", "k2"]), (0, [])]
    await cache.invalidate_tenant_cache("tenant-1")
    redis.delete.assert_any_await("k1", "k2")

    redis.scan.side_effect = RuntimeError("scan failed")
    await cache.invalidate_tenant_cache("tenant-1")


@pytest.mark.asyncio
async def test_cached_query_uses_positional_tenant_and_returns_cached_hit() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object, tenant_id: str, extra: str) -> dict[str, str]:
        return {"tenant": tenant_id, "extra": extra}

    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(return_value={"hit": True})) as mock_get,
        patch.object(cache, "_make_cache_key", wraps=cache._make_cache_key) as mock_key,
    ):
        wrapped = cache.cached_query(ttl=30, tenant_aware=True)(handler)
        assert await wrapped(object(), "tenant-123", "x") == {"hit": True}

    mock_get.assert_awaited_once()
    assert mock_key.call_args.kwargs["tenant_id"] == "tenant-123"


@pytest.mark.asyncio
async def test_cached_query_skips_lock_block_when_enabled_but_redis_removed() -> None:
    cache = QueryCache(redis_client=AsyncMock())
    cache.redis = None  # Force the branch that skips lock management while enabled remains True.

    async def handler(_db: object) -> dict[str, bool]:
        return {"ok": True}

    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(return_value=None)),
        patch.object(cache, "set_cached_result", new=AsyncMock()) as mock_set,
    ):
        wrapped = cache.cached_query()(handler)
        assert await wrapped(object()) == {"ok": True}

    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_query_lock_wait_returns_after_other_worker_fills_cache() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object) -> dict[str, bool]:
        return {"computed": True}

    redis.set = AsyncMock(return_value=False)
    with (
        patch.object(
            cache,
            "get_cached_result",
            new=AsyncMock(side_effect=[None, None, {"from_cache": True}]),
        ) as mock_get,
        patch("app.shared.core.cache.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        wrapped = cache.cached_query()(handler)
        result = await wrapped(object())

    assert result == {"from_cache": True}
    assert mock_get.await_count >= 3
    mock_sleep.assert_awaited()
    redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_cached_query_lock_acquire_exception_then_executes_query() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object) -> dict[str, str]:
        return {"ok": "value"}

    redis.set = AsyncMock(side_effect=RuntimeError("lock acquire failed"))
    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(return_value=None)),
        patch.object(cache, "set_cached_result", new=AsyncMock()) as mock_set,
    ):
        wrapped = cache.cached_query()(handler)
        assert await wrapped(object()) == {"ok": "value"}

    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_query_lock_wait_timeout_reacquire_error_falls_back_to_execution() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object) -> dict[str, str]:
        return {"computed": "value"}

    redis.set = AsyncMock(side_effect=[False, RuntimeError("reacquire failed")])
    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(side_effect=[None] * 20)),
        patch.object(cache, "set_cached_result", new=AsyncMock()) as mock_set,
        patch("app.shared.core.cache.asyncio.sleep", new=AsyncMock()),
    ):
        wrapped = cache.cached_query()(handler)
        assert await wrapped(object()) == {"computed": "value"}

    mock_set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_query_lock_reacquire_success_skips_timeout_warning() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object) -> dict[str, str]:
        return {"computed": "value"}

    redis.set = AsyncMock(side_effect=[False, True])
    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(side_effect=[None] * 20)),
        patch.object(cache, "set_cached_result", new=AsyncMock()) as mock_set,
        patch("app.shared.core.cache.asyncio.sleep", new=AsyncMock()),
        patch("app.shared.core.cache.logger") as mock_logger,
    ):
        wrapped = cache.cached_query()(handler)
        assert await wrapped(object()) == {"computed": "value"}

    mock_set.assert_awaited_once()
    warning_events = [c.args[0] for c in mock_logger.warning.call_args_list if c.args]
    assert "cache_lock_wait_timeout_fallback" not in warning_events


@pytest.mark.asyncio
async def test_cached_query_logs_lock_release_error_when_delete_fails() -> None:
    redis = AsyncMock()
    cache = QueryCache(redis_client=redis)

    async def handler(_db: object) -> dict[str, bool]:
        return {"ok": True}

    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
    with (
        patch.object(cache, "get_cached_result", new=AsyncMock(return_value=None)),
        patch.object(cache, "set_cached_result", new=AsyncMock()),
        patch("app.shared.core.cache.logger") as mock_logger,
    ):
        wrapped = cache.cached_query()(handler)
        assert await wrapped(object()) == {"ok": True}

    events = [c for c in mock_logger.warning.call_args_list if c.args and c.args[0] == "cache_lock_release_error"]
    assert events, "expected cache_lock_release_error warning"
    assert events[-1].kwargs["error"] == "delete failed"
