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
import structlog
from typing import Optional, Any
from uuid import UUID
from datetime import timedelta

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


def _get_sync_client() -> Optional[Redis]:
    """Get or create synchronous Redis client."""
    global _sync_client
    settings = get_settings()
    
    if not settings.UPSTASH_REDIS_URL or not settings.UPSTASH_REDIS_TOKEN:
        logger.debug("redis_disabled", reason="UPSTASH credentials not configured")
        return None
    
    if _sync_client is None:
        _sync_client = Redis(
            url=settings.UPSTASH_REDIS_URL,
            token=settings.UPSTASH_REDIS_TOKEN
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
            url=settings.UPSTASH_REDIS_URL,
            token=settings.UPSTASH_REDIS_TOKEN
        )
        logger.info("redis_async_client_created")
    
    return _async_client


class CacheService:
    """
    Async caching service for Valdrix.
    
    Falls back gracefully when Redis is not configured.
    """
    
    def __init__(self):
        self.client = _get_async_client()
        self.enabled = self.client is not None
    
    async def get_analysis(self, tenant_id: UUID) -> Optional[dict]:
        """Get cached LLM analysis for a tenant."""
        key = f"{PREFIX_ANALYSIS}:{tenant_id}"
        return await self._get(key)
    
    async def set_analysis(self, tenant_id: UUID, analysis: dict) -> bool:
        """Cache LLM analysis with 24h TTL."""
        key = f"{PREFIX_ANALYSIS}:{tenant_id}"
        return await self._set(key, analysis, ANALYSIS_TTL)
    
    async def get_cost_data(self, tenant_id: UUID, date_range: str) -> Optional[list]:
        """Get cached cost data for a tenant and date range."""
        key = f"{PREFIX_COSTS}:{tenant_id}:{date_range}"
        return await self._get(key)
    
    async def set_cost_data(self, tenant_id: UUID, date_range: str, costs: list) -> bool:
        """Cache cost data with 6h TTL."""
        key = f"{PREFIX_COSTS}:{tenant_id}:{date_range}"
        return await self._set(key, costs, COST_DATA_TTL)
    
    async def invalidate_tenant(self, tenant_id: UUID) -> bool:
        """Invalidate all cache entries for a tenant."""
        if not self.enabled:
            return False
        try:
            await self.client.delete(f"{PREFIX_ANALYSIS}:{tenant_id}")
            logger.info("cache_invalidated", tenant_id=str(tenant_id))
            return True
        except Exception as e:
            logger.warning("cache_invalidate_error", error=str(e))
            return False

    async def _get(self, key: str) -> Optional[Any]:
        """Internal helper for Redis GET with error handling."""
        if not self.enabled:
            return None
        try:
            data = await self.client.get(key)
            if data:
                logger.debug("cache_hit", key=key)
                return json.loads(data) if isinstance(data, str) else data
        except Exception as e:
            logger.warning("cache_get_error", key=key, error=str(e))
        return None

    async def _set(self, key: str, value: Any, ttl: timedelta) -> bool:
        """Internal helper for Redis SET with error handling."""
        if not self.enabled:
            return False
        try:
            await self.client.set(
                key,
                json.dumps(value, default=str),
                ex=int(ttl.total_seconds())
            )
            logger.debug("cache_set", key=key, ttl_seconds=int(ttl.total_seconds()))
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=key, error=str(e))
            return False


# Singleton cache service
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the global cache service."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
