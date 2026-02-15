"""
Currency Service - Multi-Currency Support for Valdrix

Provides exchange rate fetching and conversion.
Prioritizes Paystack for NGN rates to ensure alignment with user billing.
"""

import time
import httpx
from decimal import Decimal
from typing import Dict, Optional
import structlog
from app.shared.core.config import get_settings
from datetime import timedelta

logger = structlog.get_logger()

# In-memory cache for exchange rates
# key: currency_code, value: (rate_vs_usd, last_updated_timestamp)
_RATES_CACHE: Dict[str, tuple[Decimal, float]] = {"USD": (Decimal("1.0"), time.time())}

# Fallback rates (Hardcoded as a last resort)
FALLBACK_RATES = {
    "NGN": Decimal("1550.0"),  # Approximate market rate Jan 2026
    "EUR": Decimal("0.92"),
    "GBP": Decimal("0.78"),
}


async def fetch_paystack_ngn_rate() -> Optional[Decimal]:
    """
    Attempts to fetch the current NGN exchange rate from Paystack.
    Paystack uses these rates for international settlement.
    """
    settings = get_settings()
    if not settings.PAYSTACK_SECRET_KEY:
        return None

    try:
        async with httpx.AsyncClient() as client:
            # Paystack undocumented (but used by SDKs) rate endpoint
            # Fallback: We can check their balance or recent transfers if needed
            # For now, we'll try a common approach: simulating a conversion or using the decision API
            response = await client.get(
                "https://api.paystack.co/transfer/rate?from=USD&to=NGN",
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                timeout=10.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") and "data" in data:
                    rate = data["data"].get("rate")
                    if rate:
                        return Decimal(str(rate))

            logger.warning("paystack_rate_fetch_failed", status=response.status_code)
    except Exception as e:
        logger.error("paystack_rate_fetch_error", error=str(e))

    return None


async def fetch_public_exchange_rates() -> Dict[str, Decimal]:
    """
    Fetches exchange rates from a public API (e.g., ExchangeRate-API).
    Provides a professional fallback for non-Paystack markets.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Using a reliable public API for global rates
            response = await client.get(
                "https://open.er-api.com/v6/latest/USD", timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("result") == "success":
                    rates = data.get("rates", {})
                    return {k: Decimal(str(v)) for k, v in rates.items()}
    except Exception as e:
        logger.warning("public_rate_fetch_failed", error=str(e))
    return {}


async def fetch_fallback_rates() -> Dict[str, Decimal]:
    """
    Fetches exchange rates from a public API if possible.
    For MVP, we use hardcoded defaults if Paystack/Specific providers fail.
    """
    public_rates = await fetch_public_exchange_rates()
    if public_rates:
        # Merge with hardcoded defaults, public rates taking precedence
        merged = FALLBACK_RATES.copy()
        merged.update({k: v for k, v in public_rates.items() if k in FALLBACK_RATES})
        return merged
    return FALLBACK_RATES


async def get_exchange_rate(to_currency: str) -> Decimal:
    """
    Returns the exchange rate for USD to to_currency.
    Uses Redis-backed cache for cross-service consistency.
    """
    settings = get_settings()
    to_currency = to_currency.upper()

    if to_currency == "USD":
        return Decimal("1.0")

    now = time.time()

    # 1. Try In-Memory Cache (Short-lived L1)
    cached_rate, last_updated = _RATES_CACHE.get(to_currency, (None, 0))
    # sync_interval_sec unused
    if cached_rate and (now - last_updated < 300):  # 5 min in-memory stickiness
        return cached_rate

    # 2. Try Redis Cache (L2)
    from app.shared.core.cache import get_cache_service

    cache = get_cache_service()
    if cache.enabled:
        redis_key = f"currency_rate:{to_currency}"
        redis_data = await cache._get(redis_key)
        if redis_data:
            redis_rate = Decimal(str(redis_data["rate"]))
            _RATES_CACHE[to_currency] = (redis_rate, now)
            return redis_rate

    # 3. Cache expired or missing: Fetch new rate
    logger.info("syncing_exchange_rate", currency=to_currency)

    rate: Decimal | None = None
    if to_currency == "NGN":
        rate = await fetch_paystack_ngn_rate()

    if not rate:
        all_fallbacks = await fetch_fallback_rates()
        fallback_rate = all_fallbacks.get(to_currency, FALLBACK_RATES.get(to_currency))
        rate = Decimal(str(fallback_rate)) if fallback_rate is not None else None

    if rate:
        # Update L1 and L2
        _RATES_CACHE[to_currency] = (rate, now)
        if cache.enabled:
            await cache._set(
                f"currency_rate:{to_currency}",
                {"rate": float(rate), "updated_at": now},
                ttl=timedelta(hours=settings.EXCHANGE_RATE_SYNC_INTERVAL_HOURS),
            )
        return rate

    return Decimal("1.0")


async def convert_usd(amount_usd: float | Decimal, to_currency: str) -> Decimal:
    """
    Converts a USD amount to the target currency.
    """
    if to_currency.upper() == "USD":
        return Decimal(str(amount_usd))

    rate = await get_exchange_rate(to_currency)
    return Decimal(str(amount_usd)) * rate


async def convert_to_usd(amount: float | Decimal, from_currency: str) -> Decimal:
    """
    Converts an amount in `from_currency` into USD.

    `get_exchange_rate()` returns USD->X, so we invert the rate for X->USD.
    """
    currency = (from_currency or "USD").upper()
    amount_dec = Decimal(str(amount))
    if currency == "USD":
        return amount_dec

    rate = await get_exchange_rate(currency)
    if rate <= 0:
        return amount_dec
    return amount_dec / rate


async def format_currency(amount_usd: float | Decimal, to_currency: str) -> str:
    """
    Formats a USD amount for display in the target currency.
    """
    converted = await convert_usd(amount_usd, to_currency)

    symbols = {"NGN": "₦", "USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(to_currency.upper(), f"{to_currency.upper()} ")

    return f"{symbol}{float(converted):,.2f}"
