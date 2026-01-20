import asyncio
import structlog
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

class HealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_all(self) -> Dict[str, Any]:
        """Runs all dependency health checks."""
        db_ok, db_details = await self.check_database()
        redis_ok, redis_details = await self.check_redis()
        aws_ok, aws_details = await self.check_aws()

        overall_status = "healthy"
        if not db_ok:
            overall_status = "unhealthy"
        elif not redis_ok or not aws_ok:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "database": {"status": "up" if db_ok else "down", **db_details},
            "redis": {"status": "up" if redis_ok else "down", **redis_details},
            "aws": {"status": "up" if aws_ok else "down", **aws_details}
        }

    async def check_database(self) -> tuple[bool, Dict[str, Any]]:
        """Verifies database connectivity."""
        try:
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            await self.db.execute(text("SELECT 1"))
            latency = (loop.time() - start_time) * 1000
            return True, {"latency_ms": round(latency, 2)}
        except Exception as e:
            logger.error("health_check_db_failed", error=str(e))
            return False, {"error": str(e)}

    async def check_redis(self) -> tuple[bool, Dict[str, Any]]:
        """Verifies Redis connectivity (if configured)."""
        if not settings.REDIS_URL:
            return True, {"status": "skipped", "message": "Redis not configured"}
        
        try:
            from app.core.rate_limit import get_redis_client
            redis = get_redis_client()
            if not redis:
                return False, {"error": "Redis client not available"}
            
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            await redis.ping()
            latency = (loop.time() - start_time) * 1000
            return True, {"latency_ms": round(latency, 2)}
        except Exception as e:
            logger.error("health_check_redis_failed", error=str(e))
            return False, {"error": str(e)}

    async def check_aws(self) -> tuple[bool, Dict[str, Any]]:
        """Verifies AWS STS reachability."""
        try:
            # Simple check by pinging STS endpoint or using boto3
            # We use httpx for a lightweight reachability check to the STS public endpoint
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://sts.amazonaws.com")
                if response.status_code < 500: # 403/404 is still "reachable"
                    return True, {"reachable": True}
                return False, {"error": f"STS returned {response.status_code}"}
        except Exception as e:
            logger.warning("health_check_aws_sts_failed", error=str(e))
            return False, {"error": str(e)}
