import httpx
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.shared.core.config import get_settings
from app.models.pricing import ExchangeRate

logger = structlog.get_logger()
settings = get_settings()

class ExchangeRateService:
    """
    Handles USD to NGN currency conversion using ExchangeRate-API.
    Uses database as primary cache and Redis as short-term cache.
    """
    
    API_URL = "https://v6.exchangerate-api.com/v6"
    CACHE_TTL_HOURS = 24

    def __init__(self, db: AsyncSession):
        self.db = db
        self.api_key = settings.EXCHANGERATE_API_KEY

    async def get_ngn_rate(self) -> float:
        """
        Get the current USD to NGN exchange rate.
        Order of priority:
        1. DB Cache (if updated < 24h ago)
        2. External API
        3. Hardcoded Fallback (₦1,450 as of early 2026)
        """
        rate_obj = None
        # 1. Check DB Cache
        try:
            result = await self.db.execute(
                select(ExchangeRate).where(
                    ExchangeRate.from_currency == "USD",
                    ExchangeRate.to_currency == "NGN"
                )
            )
            rate_obj = result.scalar_one_or_none()
            
            if rate_obj and rate_obj.last_updated > datetime.now(timezone.utc) - timedelta(hours=self.CACHE_TTL_HOURS):
                return float(rate_obj.rate)
        except Exception as e:
            logger.warning("currency_db_cache_lookup_failed", error=str(e))

        # 2. Fetch from External API
        if self.api_key:
            try:
                rate = await self._fetch_from_api()
                await self._update_db_cache(rate)
                return rate
            except Exception as e:
                logger.error("currency_api_fetch_failed", error=str(e))

        # 3. Last Resort Fallback
        if rate_obj:
            logger.warning("currency_using_stale_db_rate", age=datetime.now(timezone.utc) - rate_obj.last_updated)
            return float(rate_obj.rate)
            
        return settings.FALLBACK_NGN_RATE  # Industry estimated baseline if all else fails

    async def _fetch_from_api(self) -> float:
        """Fetch latest rate from ExchangeRate-API."""
        url = f"{self.API_URL}/{self.api_key}/latest/USD"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if data.get("result") == "success":
                return float(data["conversion_rates"]["NGN"])
            
            raise ValueError(f"API returned failure: {data.get('error-type')}")

    async def _update_db_cache(self, rate: float):
        """Update or insert the exchange rate in the database."""
        try:
            # Check if exists
            result = await self.db.execute(
                select(ExchangeRate).where(
                    ExchangeRate.from_currency == "USD",
                    ExchangeRate.to_currency == "NGN"
                )
            )
            rate_obj = result.scalar_one_or_none()
            
            if rate_obj:
                rate_obj.rate = rate
                rate_obj.last_updated = datetime.now(timezone.utc)
            else:
                new_rate = ExchangeRate(
                    from_currency="USD",
                    to_currency="NGN",
                    rate=rate,
                    last_updated=datetime.now(timezone.utc)
                )
                from app.shared.core.async_utils import maybe_await
                await maybe_await(self.db.add(new_rate))
            
            await self.db.commit()
            logger.info("currency_db_cache_updated", rate=rate)
        except Exception as e:
            logger.error("currency_db_cache_update_failed", error=str(e))
            await self.db.rollback()

    def convert_usd_to_ngn(self, usd_amount: float, rate: float) -> int:
        """
        Converts USD to NGN subunits (Kobo).
        Paystack expects amounts in subunits.
        """
        ngn_amount = usd_amount * rate
        # Round to nearest Kobo to avoid unnecessary precision loss.
        return int(round(ngn_amount * 100))
