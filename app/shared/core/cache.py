"""
Redis Cache Service using Upstash Redis

Provides async caching for:
- LLM analysis results (24h TTL)
- Cost data (6h TTL)
- Tenant metadata (1h TTL)

Uses Upstash free tier (10K commands/day) which is sufficient for:
- 100 tenants × 10 cache ops/day = 1000 ops
- Even at 1000 tenants = 10K ops/day (fits free tier)
"""

import json
import hashlib
import structlog
import asyncio
from typing import Any, Optional
from uuid import UUID
from datetime import timedelta
from functools import wraps
from collections.abc import Callable

from upstash_redis import Redis
from upstash_redis.asyncio import Redis as AsyncRedis

from app.shared.core.config import get_settings

logger = structlog.get_logger()

# Cache TTLs
ANALYSIS_TTL = timedelta(hours=24)
COST_DATA_TTL = timedelta(hours=6)
METADATA_TTL = timedelta(hours=1)

# Key Prefixes
PREFIX_ANALYSIS = "analysis"
PREFIX_COSTS = "costs"

# Singleton instances
_sync_client: Optional[Redis] = None
_async_client: Optional[AsyncRedis] = None


def _safe_json_loads(payload: str, key: str) -> Optional[Any]:
    """Strict JSON decode with bounded-failure behavior."""
    try:
        return json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("cache_payload_invalid_json", key=key, error=str(exc))
        return None


def _get_sync_client() -> Optional[Redis]:
    """Get or create synchronous Redis client."""
    global _sync_client
    settings = get_settings()

    if not settings.UPSTASH_REDIS_URL or not settings.UPSTASH_REDIS_TOKEN:
        logger.debug("redis_disabled", reason="UPSTASH credentials not configured")
        return None

    if _sync_client is None:
        _sync_client = Redis(
            url=settings.UPSTASH_REDIS_URL, token=settings.UPSTASH_REDIS_TOKEN
        )
        logger.info("redis_sync_client_created")

    return _sync_client


def _get_async_client() -> Optional[AsyncRedis]:
    """Get or create async Redis client."""
    global _async_client
    settings = get_settings()

    if not settings.UPSTASH_REDIS_URL or not settings.UPSTASH_REDIS_TOKEN:
        logger.debug("redis_disabled", reason="UPSTASH credentials not configured")
        return None

    if _async_client is None:
        _async_client = AsyncRedis(
            url=settings.UPSTASH_REDIS_URL, token=settings.UPSTASH_REDIS_TOKEN
        )
        logger.info("redis_async_client_created")

    return _async_client


class CacheService:
    """
    Async caching service for Valdrix.

    Falls back gracefully when Redis is not configured.
    """

    def __init__(self) -> None:
        self.client = _get_async_client()
        self.enabled = self.client is not None

    async def get_analysis(self, tenant_id: UUID) -> Optional[dict[str, Any]]:
        """Get cached LLM analysis for a tenant."""
        key = f"{PREFIX_ANALYSIS}:{tenant_id}"
        return await self._get(key)

    async def set_analysis(self, tenant_id: UUID, analysis: dict[str, Any]) -> bool:
        """Cache LLM analysis with 24h TTL."""
        key = f"{PREFIX_ANALYSIS}:{tenant_id}"
        return await self._set(key, analysis, ANALYSIS_TTL)

    async def get_cost_data(
        self, tenant_id: UUID, date_range: str
    ) -> Optional[list[Any]]:
        """Get cached cost data for a tenant and date range."""
        key = f"{PREFIX_COSTS}:{tenant_id}:{date_range}"
        return await self._get(key)

    async def set_cost_data(
        self, tenant_id: UUID, date_range: str, costs: list[Any]
    ) -> bool:
        """Cache cost data with 6h TTL."""
        key = f"{PREFIX_COSTS}:{tenant_id}:{date_range}"
        return await self._set(key, costs, COST_DATA_TTL)

    async def invalidate_tenant(self, tenant_id: UUID) -> bool:
        """Invalidate all cache entries for a tenant."""
        if not self.enabled or self.client is None:
            return False
        try:
            await self.client.delete(f"{PREFIX_ANALYSIS}:{tenant_id}")
            logger.info("cache_invalidated", tenant_id=str(tenant_id))
            return True
        except Exception as e:
            logger.warning("cache_invalidate_error", error=str(e))
            return False

    async def get(self, key: str) -> Optional[Any]:
        """Public helper for Redis GET."""
        return await self._get(key)

    async def set(self, key: str, value: Any, ttl: Optional[timedelta] = None) -> bool:
        """Public helper for Redis SET."""
        return await self._set(key, value, ttl or ANALYSIS_TTL)

    async def delete_pattern(self, pattern: str) -> bool:
        """Delete keys matching pattern."""
        if not self.enabled or self.client is None:
            return False
        try:
            scan_iter = getattr(self.client, "scan_iter", None)
            if callable(scan_iter):
                keys = [key async for key in scan_iter(match=pattern)]
                if keys:
                    await self.client.delete(*keys)
                    logger.info(
                        "cache_pattern_deleted", pattern=pattern, count=len(keys)
                    )
                return True

            cursor = 0
            total_deleted = 0
            while True:
                next_cursor, keys = await self.client.scan(
                    cursor, match=pattern, count=100
                )
                if keys:
                    await self.client.delete(*keys)
                    total_deleted += len(keys)
                cursor = int(next_cursor)
                if cursor == 0:
                    break
            if total_deleted > 0:
                logger.info(
                    "cache_pattern_deleted", pattern=pattern, count=total_deleted
                )
            return True
        except Exception as e:
            logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return False

    async def _get(self, key: str) -> Optional[Any]:
        """Internal helper for Redis GET with error handling."""
        if not self.enabled or self.client is None:
            return None
        try:
            data = await self.client.get(key)
            if data is not None:
                logger.debug("cache_hit", key=key)
                if isinstance(data, bytes):
                    try:
                        data = data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        logger.warning(
                            "cache_payload_invalid_encoding", key=key, error=str(exc)
                        )
                        return None
                if isinstance(data, str):
                    return _safe_json_loads(data, key=key)
                if isinstance(data, (dict, list, int, float, bool)):
                    return data
                if data is None:
                    return None
                logger.warning(
                    "cache_payload_unexpected_type",
                    key=key,
                    payload_type=type(data).__name__,
                )
                return None
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
        return None

    async def _set(self, key: str, value: Any, ttl: timedelta) -> bool:
        """Internal helper for Redis SET with error handling."""
        if not self.enabled or self.client is None:
            return False
        try:
            await self.client.set(
                key, json.dumps(value, default=str), ex=int(ttl.total_seconds())
            )
            logger.debug("cache_set", key=key, ttl_seconds=int(ttl.total_seconds()))
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False


class QueryCache:
    """Query result caching with automatic invalidation."""

    def __init__(self, redis_client: Any = None, default_ttl: int = 300) -> None:
        self.redis = redis_client
        self.default_ttl = default_ttl
        self.enabled = redis_client is not None

    def _make_cache_key(
        self, query: str, params: dict[str, Any], tenant_id: Optional[str] = None
    ) -> str:
        """Generate deterministic cache key from query and parameters."""
        key_data = {"query": query, "params": params, "tenant_id": tenant_id}
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        digest = hashlib.sha256(key_str.encode()).hexdigest()
        if tenant_id:
            return f"query_cache:tenant:{tenant_id}:{digest}"
        return f"query_cache:{digest}"

    async def get_cached_result(self, cache_key: str) -> Optional[Any]:
        """Retrieve cached query result."""
        if not self.enabled or self.redis is None:
            return None

        try:
            cached_data = await self.redis.get(cache_key)
            if cached_data is not None:
                logger.debug("cache_hit", key=cache_key)
                if isinstance(cached_data, bytes):
                    try:
                        cached_data = cached_data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        logger.warning(
                            "cache_payload_invalid_encoding",
                            key=cache_key,
                            error=str(exc),
                        )
                        return None
                if isinstance(cached_data, str):
                    return _safe_json_loads(cached_data, key=cache_key)
                if isinstance(cached_data, (dict, list, int, float, bool)):
                    return cached_data
                logger.warning(
                    "cache_payload_unexpected_type",
                    key=cache_key,
                    payload_type=type(cached_data).__name__,
                )
                return None
            logger.debug("cache_miss", key=cache_key)
            return None
        except Exception as e:
            logger.warning("cache_get_error", error=str(e), key=cache_key)
            return None

    async def set_cached_result(
        self, cache_key: str, result: Any, ttl: Optional[int] = None
    ) -> None:
        """Cache query result with TTL."""
        if not self.enabled or self.redis is None:
            return

        try:
            ttl = ttl or self.default_ttl
            await self.redis.set(cache_key, json.dumps(result, default=str), ex=ttl)
            logger.debug("cache_set", key=cache_key, ttl=ttl)
        except Exception as e:
            logger.warning("cache_set_error", error=str(e), key=cache_key)

    async def invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Invalidate all cached queries for a tenant."""
        if not self.enabled or self.redis is None:
            return

        try:
            # Use Redis SCAN to find tenant-related keys
            pattern = f"query_cache:tenant:{tenant_id}:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                if keys:
                    # Use a transaction/pipeline for atomic deletion if supported, 
                    # or just delete the batch. Upstash-redis-python handles delete(*keys).
                    await self.redis.delete(*keys)
                    logger.info(
                        "cache_invalidated", tenant_id=tenant_id, keys_deleted=len(keys)
                    )
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(
                "cache_invalidation_error", error=str(e), tenant_id=tenant_id
            )

    def cached_query(
        self,
        ttl: Optional[int] = None,
        tenant_aware: bool = True,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """
        Decorator for caching SQLAlchemy query results.

        Usage:
            @cache.cached_query(ttl=300, tenant_aware=True)
            async def get_tenant_connections(db, tenant_id):
                return await db.execute(select(AWSConnection).where(...))
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self.enabled:
                    return await func(*args, **kwargs)

                # Extract tenant_id for tenant-aware caching
                tenant_id = None
                if tenant_aware:
                    # Look for tenant_id in kwargs or as second positional arg (after db)
                    tenant_id = kwargs.get("tenant_id") or (
                        args[1] if len(args) > 1 else None
                    )

                # Generate cache key from function name and arguments
                cache_key = self._make_cache_key(
                    query=func.__name__,
                    params={
                        "args": args[2:],
                        "kwargs": {k: v for k, v in kwargs.items() if k != "tenant_id"},
                    },
                    tenant_id=str(tenant_id) if tenant_id else None,
                )

                # Try cache first
                cached_result = await self.get_cached_result(cache_key)
                if cached_result is not None:
                    return cached_result

                # SEC: Dogpile/Stampede Protection (BE-CORE-1)
                # Use a short-lived lock to ensure only one worker executes the query.
                lock_key = f"lock:{cache_key}"
                lock_acquired = False
                if self.redis:
                    lock_ttl_seconds = 30
                    wait_step_seconds = 0.25
                    max_wait_seconds = 2.0
                    try:
                        # SET NX (if not exists) EX (expire)
                        lock_acquired = bool(
                            await self.redis.set(
                                lock_key,
                                "locked",
                                ex=lock_ttl_seconds,
                                nx=True,
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            "cache_lock_acquire_error",
                            key=lock_key,
                            error=str(e),
                        )
                        lock_acquired = False

                    # If another worker holds the lock, wait for cache fill and retry once.
                    if not lock_acquired:
                        waited = 0.0
                        while waited < max_wait_seconds:
                            await asyncio.sleep(wait_step_seconds)
                            waited += wait_step_seconds
                            cached_result = await self.get_cached_result(cache_key)
                            if cached_result is not None:
                                return cached_result
                        try:
                            lock_acquired = bool(
                                await self.redis.set(
                                    lock_key,
                                    "locked",
                                    ex=lock_ttl_seconds,
                                    nx=True,
                                )
                            )
                        except Exception as e:
                            logger.warning(
                                "cache_lock_reacquire_error",
                                key=lock_key,
                                error=str(e),
                            )
                            lock_acquired = False
                        if not lock_acquired:
                            logger.warning(
                                "cache_lock_wait_timeout_fallback",
                                key=cache_key,
                                wait_seconds=max_wait_seconds,
                            )

                try:
                    # Execute query
                    result = await func(*args, **kwargs)

                    # Cache result
                    await self.set_cached_result(cache_key, result, ttl)
                finally:
                    # Release lock
                    if self.redis and lock_acquired:
                        try:
                            await self.redis.delete(lock_key)
                        except Exception as e:
                            logger.warning(
                                "cache_lock_release_error",
                                key=lock_key,
                                error=str(e),
                            )

                return result

            return wrapper

        return decorator


# Singleton cache service
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the global cache service."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
