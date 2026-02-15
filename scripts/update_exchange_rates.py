import asyncio
import os
import aiohttp
import structlog
from datetime import datetime, timezone
from app.shared.db.session import async_session_maker
from app.models.pricing import ExchangeRate
from sqlalchemy import select

logger = structlog.get_logger()

# In production, use a secure secret for API_KEY
EXCHANGE_RATE_API_KEY = os.environ.get("EXCHANGE_RATE_API_KEY")
EXCHANGE_RATE_API_URL = (
    f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATE_API_KEY}/latest/USD"
    if EXCHANGE_RATE_API_KEY
    else "https://open.er-api.com/v6/latest/USD"
)
PROVIDER = "exchangerate-api" if EXCHANGE_RATE_API_KEY else "open.er-api"

# Only update existing currencies if present; otherwise use a safe default list.
DEFAULT_CURRENCIES = {"NGN", "EUR", "GBP"}


async def update_exchange_rates():
    """
    Fetches latest exchange rates and updates the database.
    Standardizes BE-FIN-01: Automated Exchange Rate Management.
    """
    logger.info("exchange_rate_update_starting")

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(EXCHANGE_RATE_API_URL) as response:
                if response.status != 200:
                    raise RuntimeError(f"Exchange rate API error: {response.status}")
                data = await response.json()

        if data.get("result") != "success":
            raise RuntimeError(f"Exchange rate API failed: {data}")

        rates = data.get("conversion_rates") or data.get("rates") or {}
        if not rates:
            raise RuntimeError("Exchange rate API returned no rates")

        async with async_session_maker() as session:
            # Determine which currencies to update
            result = await session.execute(select(ExchangeRate))
            existing_rates = result.scalars().all()
            existing_map = {r.to_currency: r for r in existing_rates}
            target_currencies = set(existing_map.keys()) or DEFAULT_CURRENCIES

            for currency in target_currencies:
                rate_val = rates.get(currency)
                if rate_val is None:
                    logger.warning("exchange_rate_missing_currency", currency=currency)
                    continue
                rate = float(rate_val)

                stmt = select(ExchangeRate).where(
                    ExchangeRate.from_currency == "USD",
                    ExchangeRate.to_currency == currency,
                )
                result = await session.execute(stmt)
                db_rate = result.scalar_one_or_none()

                if db_rate:
                    logger.info("updating_existing_rate", currency=currency, rate=rate)
                    db_rate.rate = rate
                    db_rate.provider = PROVIDER
                    db_rate.last_updated = datetime.now(timezone.utc)
                else:
                    logger.info("creating_new_rate", currency=currency, rate=rate)
                    new_rate = ExchangeRate(
                        from_currency="USD",
                        to_currency=currency,
                        rate=rate,
                        provider=PROVIDER,
                    )
                    session.add(new_rate)

            await session.commit()
            logger.info("exchange_rate_update_complete")

    except Exception as e:
        logger.error("exchange_rate_update_failed", error=str(e))


if __name__ == "__main__":
    asyncio.run(update_exchange_rates())
