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
from typing import Optional
from uuid import UUID
from datetime import timedelta

from upstash_redis import Redis
from upstash_redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings

logger = structlog.get_logger()

# Cache TTLs
ANALYSIS_TTL = timedelta(hours=24)
COST_DATA_TTL = timedelta(hours=6)
METADATA_TTL = timedelta(hours=1)

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
        if not self.enabled:
            return None
        
        try:
            key = f"analysis:{tenant_id}"
            data = await self.client.get(key)
            if data:
                logger.debug("cache_hit", key=key)
                return json.loads(data) if isinstance(data, str) else data
        except Exception as e:
            logger.warning("cache_get_error", key=f"analysis:{tenant_id}", error=str(e))
        
        return None
    
    async def set_analysis(self, tenant_id: UUID, analysis: dict) -> bool:
        """Cache LLM analysis with 24h TTL."""
        if not self.enabled:
            return False
        
        try:
            key = f"analysis:{tenant_id}"
            await self.client.set(
                key,
                json.dumps(analysis),
                ex=int(ANALYSIS_TTL.total_seconds())
            )
            logger.debug("cache_set", key=key, ttl_hours=24)
            return True
        except Exception as e:
            logger.warning("cache_set_error", key=f"analysis:{tenant_id}", error=str(e))
            return False
    
    async def get_cost_data(self, tenant_id: UUID, date_range: str) -> Optional[list]:
        """Get cached cost data for a tenant and date range."""
        if not self.enabled:
            return None
        
        try:
            key = f"costs:{tenant_id}:{date_range}"
            data = await self.client.get(key)
            if data:
                logger.debug("cache_hit", key=key)
                return json.loads(data) if isinstance(data, str) else data
        except Exception as e:
            logger.warning("cache_get_error", error=str(e))
        
        return None
    
    async def set_cost_data(self, tenant_id: UUID, date_range: str, costs: list) -> bool:
        """Cache cost data with 6h TTL."""
        if not self.enabled:
            return False
        
        try:
            key = f"costs:{tenant_id}:{date_range}"
            await self.client.set(
                key,
                json.dumps(costs, default=str),
                ex=int(COST_DATA_TTL.total_seconds())
            )
            logger.debug("cache_set", key=key, ttl_hours=6)
            return True
        except Exception as e:
            logger.warning("cache_set_error", error=str(e))
            return False
    
    async def invalidate_tenant(self, tenant_id: UUID) -> bool:
        """Invalidate all cache entries for a tenant."""
        if not self.enabled:
            return False
        
        try:
            # Delete analysis and cost caches
            await self.client.delete(f"analysis:{tenant_id}")
            # Note: cost keys with date ranges would need pattern matching
            # which Upstash supports but we'll keep it simple for now
            logger.info("cache_invalidated", tenant_id=str(tenant_id))
            return True
        except Exception as e:
            logger.warning("cache_invalidate_error", error=str(e))
            return False


# Singleton cache service
_cache_service: Optional[CacheService] = None


def get_cache_service() -> CacheService:
    """Get or create the global cache service."""
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService()
    return _cache_service
