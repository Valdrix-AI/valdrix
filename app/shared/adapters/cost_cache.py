"""
Cost Result Caching - Production Ready

Implements a caching strategy for cloud cost results with:
1. Redis backend for production (distributed, persistent)
2. In-memory fallback for development
3. Automatic TTL management
4. Cache invalidation support

Cost Benefits:
- Reduces external ingestion overhead
- Improves response times (cache hits < 10ms)
- Enables offline analysis
"""

import json
import hashlib
import asyncio
from abc import ABC, abstractmethod
from datetime import date, timedelta, datetime, timezone
from typing import Any, Optional, cast
import structlog

from app.shared.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def _safe_json_loads(raw_payload: Any, *, key: str) -> Any | None:
    """Decode cached JSON defensively to avoid malformed payload crashes."""
    if raw_payload is None:
        return None

    if isinstance(raw_payload, bytes):
        try:
            raw_payload = raw_payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning(
                "cost_cache_payload_invalid_encoding", key=key, error=str(exc)
            )
            return None

    if not isinstance(raw_payload, str):
        logger.warning(
            "cost_cache_payload_unexpected_type",
            key=key,
            payload_type=type(raw_payload).__name__,
        )
        return None

    try:
        return json.loads(raw_payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("cost_cache_payload_invalid_json", key=key, error=str(exc))
        return None


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        raise NotImplementedError()

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Set value in cache with TTL."""
        raise NotImplementedError()

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key from cache."""
        raise NotImplementedError()

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern. Returns count deleted."""
        raise NotImplementedError()

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        raise NotImplementedError()


class InMemoryCache(CacheBackend):
    """
    Simple in-memory cache for development/testing.

    Note: Not suitable for production multi-instance deployments.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, datetime | None]] = {}

    async def get(self, key: str) -> Optional[str]:
        if key not in self._store:
            return None

        value, expires_at = self._store[key]
        if expires_at and datetime.now(timezone.utc) > expires_at:
            del self._store[key]
            return None

        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        # Simple pattern matching (prefix only)
        prefix = pattern.rstrip("*")
        to_delete = [k for k in self._store if k.startswith(prefix)]
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    async def health_check(self) -> bool:
        return True


class RedisCache(CacheBackend):
    """
    Redis-backed cache for production.

    Features:
    - Connection pooling
    - Automatic reconnection
    - Pattern-based deletion for invalidation
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Any | None = None
        self._connected = False

    async def _get_client(self) -> Any | None:
        if self._client is None and self.redis_url:
            try:
                import redis.asyncio as aioredis

                self._client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                self._connected = True
                logger.info("redis_connected", url=self.redis_url.split("@")[-1])
            except Exception as e:
                logger.error("redis_connection_failed", error=str(e))
                self._connected = False
                return None
        return self._client

    async def get(self, key: str) -> Optional[str]:
        client = await self._get_client()
        if client is None:
            return None
        try:
            return cast(Optional[str], await client.get(key))
        except Exception as e:
            logger.warning("redis_get_failed", key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        client = await self._get_client()
        if client is None:
            return
        try:
            await client.setex(key, ttl_seconds, value)
        except Exception as e:
            logger.warning("redis_set_failed", key=key, error=str(e))

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        if client is None:
            return
        try:
            await client.delete(key)
        except Exception as e:
            logger.warning("redis_delete_failed", key=key, error=str(e))

    async def delete_pattern(self, pattern: str) -> int:
        client = await self._get_client()
        if client is None:
            return 0
        try:
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
            return deleted
        except Exception as e:
            logger.warning("redis_delete_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def health_check(self) -> bool:
        client = await self._get_client()
        if client is None:
            return False
        try:
            await client.ping()
            return True
        except Exception:
            return False


class CostCache:
    """
    High-level caching API for cost data.

    Usage:
        cache = await get_cost_cache()

        # Check cache first
        cached = await cache.get_daily_costs(tenant_id, start, end)
        if cached:
            return cached

        # Fetch from API
        costs = await adapter.get_daily_costs(start, end)

        # Store in cache
        await cache.set_daily_costs(tenant_id, start, end, costs)
    """

    # Cache TTLs
    TTL_DAILY_COSTS = 3600  # 1 hour
    TTL_ZOMBIES = 1800  # 30 minutes
    TTL_ANALYSIS = 7200  # 2 hours

    def __init__(self, backend: CacheBackend):
        self.backend = backend

    def _generate_key(self, prefix: str, tenant_id: str, *args: object) -> str:
        """Generate a unique cache key."""
        key_parts = [prefix, tenant_id] + [str(a) for a in args]
        key_string = ":".join(key_parts)
        # Switch from MD5 to SHA256 for stronger collision resistance (SEC-05)
        digest = hashlib.sha256(key_string.encode()).hexdigest()
        # Keep tenant and prefix in plaintext to allow precise invalidation patterns.
        return f"valdrix:{tenant_id}:{prefix}:{digest}"

    def _tenant_pattern(self, tenant_id: str) -> str:
        """Generate pattern for all tenant keys."""
        return f"valdrix:{tenant_id}:*"

    # Daily Costs
    async def get_daily_costs(
        self, tenant_id: str, start_date: date, end_date: date
    ) -> Optional[list[dict[str, Any]]]:
        """Get cached daily costs if available."""
        key = self._generate_key("costs", tenant_id, start_date, end_date)
        cached = await self.backend.get(key)

        if cached is not None:
            logger.debug("cache_hit", type="daily_costs", tenant_id=tenant_id)
            return _safe_json_loads(cached, key=key)

        logger.debug("cache_miss", type="daily_costs", tenant_id=tenant_id)
        return None

    async def set_daily_costs(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date,
        costs: list[dict[str, Any]],
    ) -> None:
        """Cache daily costs."""
        key = self._generate_key("costs", tenant_id, start_date, end_date)
        await self.backend.set(key, json.dumps(costs), self.TTL_DAILY_COSTS)
        logger.debug("cache_set", type="daily_costs", records=len(costs))

    # Zombie Scans
    async def get_zombie_scan(
        self, tenant_id: str, region: str
    ) -> Optional[dict[str, Any]]:
        """Get cached zombie scan if available."""
        key = self._generate_key("zombies", tenant_id, region)
        cached = await self.backend.get(key)

        if cached is not None:
            logger.debug("cache_hit", type="zombie_scan", region=region)
            return _safe_json_loads(cached, key=key)
        return None

    async def set_zombie_scan(
        self, tenant_id: str, region: str, zombies: dict[str, Any]
    ) -> None:
        """Cache zombie scan results."""
        key = self._generate_key("zombies", tenant_id, region)
        await self.backend.set(key, json.dumps(zombies), self.TTL_ZOMBIES)

    # LLM Analysis
    async def get_analysis(
        self, tenant_id: str, analysis_hash: str
    ) -> Optional[dict[str, Any]]:
        """Get cached LLM analysis if available."""
        key = self._generate_key("analysis", tenant_id, analysis_hash)
        cached = await self.backend.get(key)

        if cached is not None:
            logger.debug("cache_hit", type="analysis")
            return _safe_json_loads(cached, key=key)
        return None

    async def set_analysis(
        self, tenant_id: str, analysis_hash: str, result: dict[str, Any]
    ) -> None:
        """Cache LLM analysis results."""
        key = self._generate_key("analysis", tenant_id, analysis_hash)
        await self.backend.set(key, json.dumps(result), self.TTL_ANALYSIS)

    # Invalidation
    async def invalidate_tenant(self, tenant_id: str) -> int:
        """
        Invalidate all cache entries for a tenant.

        Use on:
        - AWS connection change
        - Settings update
        - Manual refresh request
        """
        pattern = self._tenant_pattern(tenant_id)
        deleted = await self.backend.delete_pattern(pattern)
        logger.info("cache_invalidated", tenant_id=tenant_id, keys_deleted=deleted)
        return deleted

    async def invalidate_zombies(self, tenant_id: str) -> int:
        """Invalidate zombie scan cache for fresh scan."""
        pattern = f"valdrix:{tenant_id}:zombies:*"
        deleted = await self.backend.delete_pattern(pattern)
        logger.debug("zombie_cache_invalidated", tenant_id=tenant_id, keys=deleted)
        return deleted

    # Health
    async def health_check(self) -> dict[str, Any]:
        """Check cache health for monitoring."""
        healthy = await self.backend.health_check()
        backend_type = "redis" if isinstance(self.backend, RedisCache) else "memory"
        return {
            "healthy": healthy,
            "backend": backend_type,
            "ttl_costs": self.TTL_DAILY_COSTS,
            "ttl_zombies": self.TTL_ZOMBIES,
        }


# Factory
_cache_instance: Optional[CostCache] = None
_cache_instance_lock = asyncio.Lock()


async def get_cost_cache() -> CostCache:
    """
    Factory to get cache instance.

    Uses Redis if REDIS_URL is configured, otherwise in-memory.
    Singleton pattern for connection reuse.
    """
    global _cache_instance

    if _cache_instance is None:
        async with _cache_instance_lock:
            if _cache_instance is None:
                backend: CacheBackend
                if settings.REDIS_URL:
                    backend = RedisCache(settings.REDIS_URL)
                    if await backend.health_check():
                        logger.info("cost_cache_initialized", backend="redis")
                    else:
                        logger.warning("redis_unhealthy_using_memory")
                        backend = InMemoryCache()
                else:
                    backend = InMemoryCache()
                    logger.info("cost_cache_initialized", backend="memory")

                _cache_instance = CostCache(backend)

    return _cache_instance
