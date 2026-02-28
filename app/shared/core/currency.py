"""
Unified currency service for billing, reporting, and scheduler jobs.

This module is the single source of truth for USD->X exchange rates:
- NGN priority source: CBN NFEM official endpoint.
- Cache hierarchy: in-memory (L1), Redis (L2), Postgres `exchange_rates` (L3).

Billing callers must use strict mode to fail closed when no trustworthy live rate exists.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
import time
from typing import Any, AsyncGenerator, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pricing import ExchangeRate
from app.shared.core.config import get_settings

logger = structlog.get_logger()

# L1 cache payload:
# key: currency code
# value: (rate_vs_usd, updated_timestamp, provider_name)
_RATES_CACHE: dict[str, tuple[Decimal, float, Optional[str]]] = {
    "USD": (Decimal("1.0"), time.time(), "internal")
}
_L1_TTL_SECONDS = 300.0


class ExchangeRateUnavailableError(RuntimeError):
    """Raised when strict callers cannot obtain a trustworthy FX rate."""


class ExchangeRateService:
    """Canonical FX service used by billing and non-billing consumers."""

    CBN_NFEM_URL = "https://www.cbn.gov.ng/api/GetAllNFEM_RatesGRAPH"

    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self.settings = get_settings()
        self.cache_ttl_hours = max(
            1, int(self.settings.EXCHANGE_RATE_SYNC_INTERVAL_HOURS)
        )

    @asynccontextmanager
    async def _session_scope(self) -> AsyncGenerator[AsyncSession, None]:
        if self.db is not None:
            yield self.db
            return

        from app.shared.db.session import async_session_maker

        async with async_session_maker() as session:
            # Global FX table is RLS-exempt, but mark as explicit system context.
            from app.shared.db.session import mark_session_system_context

            await mark_session_system_context(session)
            yield session

    @staticmethod
    def _normalize_currency(currency: str | None) -> str:
        return (currency or "USD").strip().upper()

    @staticmethod
    def _read_l1_rate(
        currency: str,
    ) -> tuple[Optional[Decimal], float, Optional[str]]:
        raw = _RATES_CACHE.get(currency)
        if raw is None:
            return None, 0.0, None
        rate, updated_at, provider = raw
        return rate, float(updated_at), provider

    @staticmethod
    def _write_l1_rate(currency: str, rate: Decimal, provider: Optional[str]) -> None:
        _RATES_CACHE[currency] = (rate, time.time(), provider)

    async def _read_db_rate(
        self, to_currency: str
    ) -> tuple[Optional[Decimal], Optional[datetime], Optional[str]]:
        try:
            async with self._session_scope() as session:
                result = await session.execute(
                    select(ExchangeRate).where(
                        ExchangeRate.from_currency == "USD",
                        ExchangeRate.to_currency == to_currency,
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None, None, None
                updated = row.last_updated
                # Normalize timezone-aware arithmetic.
                if updated is not None and updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                return Decimal(str(row.rate)), updated, row.provider
        except Exception as exc:
            logger.warning(
                "exchange_rate_db_read_failed",
                currency=to_currency,
                error=str(exc),
            )
            return None, None, None

    async def _upsert_db_rate(
        self, to_currency: str, rate: Decimal, provider: str
    ) -> None:
        async with self._session_scope() as session:
            try:
                result = await session.execute(
                    select(ExchangeRate).where(
                        ExchangeRate.from_currency == "USD",
                        ExchangeRate.to_currency == to_currency,
                    )
                )
                row = result.scalar_one_or_none()
                now_utc = datetime.now(timezone.utc)
                if row:
                    row.rate = float(rate)
                    row.provider = provider
                    row.last_updated = now_utc
                else:
                    session.add(
                        ExchangeRate(
                            from_currency="USD",
                            to_currency=to_currency,
                            rate=float(rate),
                            provider=provider,
                            last_updated=now_utc,
                        )
                    )
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.warning(
                    "exchange_rate_db_upsert_failed",
                    currency=to_currency,
                    provider=provider,
                    error=str(exc),
                )

    async def _read_redis_rate(
        self, to_currency: str
    ) -> tuple[Optional[Decimal], Optional[float], Optional[str]]:
        from app.shared.core.cache import get_cache_service

        cache = get_cache_service()
        if not cache.enabled:
            return None, None, None

        key = f"currency_rate:{to_currency}"
        payload = await cache._get(key)
        if not isinstance(payload, dict):
            return None, None, None

        raw_rate = payload.get("rate")
        if raw_rate is None:
            return None, None, None

        try:
            rate = Decimal(str(raw_rate))
        except Exception:
            return None, None, None

        updated = payload.get("updated_at")
        updated_ts = float(updated) if isinstance(updated, (float, int, str)) else None
        provider = payload.get("provider")
        provider_name = str(provider) if isinstance(provider, str) else None
        return rate, updated_ts, provider_name

    async def _write_redis_rate(
        self,
        to_currency: str,
        rate: Decimal,
        provider: Optional[str],
    ) -> None:
        from app.shared.core.cache import get_cache_service

        cache = get_cache_service()
        if not cache.enabled:
            return
        try:
            await cache._set(
                f"currency_rate:{to_currency}",
                {
                    "rate": float(rate),
                    "updated_at": time.time(),
                    "provider": provider,
                },
                ttl=timedelta(hours=self.cache_ttl_hours),
            )
        except Exception as exc:
            logger.debug(
                "exchange_rate_redis_write_failed",
                currency=to_currency,
                error=str(exc),
            )

    @staticmethod
    def _is_fresh(updated_at: Optional[datetime], max_age_hours: int) -> bool:
        if updated_at is None:
            return False
        return updated_at >= datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    @staticmethod
    def _parse_cbn_date(value: Any) -> Optional[datetime]:
        if not isinstance(value, str):
            return None
        raw = value.strip()
        for fmt in ("%B-%d-%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    async def _fetch_ngn_from_cbn(self) -> Decimal:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.get(self.CBN_NFEM_URL, timeout=10.0)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError("CBN NFEM payload is empty or invalid")

        latest_row = None
        latest_date = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed_date = self._parse_cbn_date(row.get("ratedate"))
            if parsed_date is None:
                continue
            if latest_date is None or parsed_date > latest_date:
                latest_date = parsed_date
                latest_row = row

        if latest_row is None:
            raise ValueError("CBN NFEM payload has no parseable rate rows")

        raw_rate = latest_row.get("weightedAvgRate") or latest_row.get("closingrate")
        if raw_rate in (None, ""):
            raise ValueError("CBN NFEM row missing weightedAvgRate/closingrate")

        rate = Decimal(str(raw_rate))
        if rate <= 0:
            raise ValueError("CBN NFEM returned non-positive rate")
        return rate

    async def _fetch_live_rate(self, to_currency: str) -> tuple[Decimal, str]:
        if to_currency == "NGN":
            try:
                return await self._fetch_ngn_from_cbn(), "cbn_nfem"
            except Exception as exc:
                raise ValueError(f"cbn_nfem:{exc}") from exc

        raise ValueError(f"no live provider configured for {to_currency}")

    async def get_rate(self, to_currency: str, *, strict: bool = False) -> Decimal:
        """
        Return USD->to_currency rate.

        strict=False:
        - may use stale DB value when all providers fail
        - returns 1.0 when no known rate exists

        strict=True:
        - stale/no-data falls through as ExchangeRateUnavailableError
        """
        currency = self._normalize_currency(to_currency)
        if currency == "USD":
            return Decimal("1.0")

        now_ts = time.time()
        max_age_seconds = self.cache_ttl_hours * 3600

        # L1: in-memory cache
        l1_rate, l1_updated_ts, l1_provider = self._read_l1_rate(currency)
        if l1_rate and (now_ts - l1_updated_ts) <= _L1_TTL_SECONDS:
            if strict and currency == "NGN" and l1_provider != "cbn_nfem":
                logger.warning(
                    "strict_ngn_ignoring_non_official_l1_rate",
                    provider=l1_provider,
                )
            else:
                return l1_rate

        # L2: Redis cache
        redis_rate, redis_updated_ts, redis_provider = await self._read_redis_rate(
            currency
        )
        if (
            redis_rate
            and redis_updated_ts
            and (now_ts - redis_updated_ts) <= max_age_seconds
        ):
            if strict and currency == "NGN" and redis_provider != "cbn_nfem":
                logger.warning(
                    "strict_ngn_ignoring_non_official_redis_rate",
                    provider=redis_provider,
                )
            else:
                self._write_l1_rate(currency, redis_rate, redis_provider)
                return redis_rate

        # L3: DB cache
        db_rate, db_updated_at, db_provider = await self._read_db_rate(currency)
        if db_rate and self._is_fresh(db_updated_at, self.cache_ttl_hours):
            if strict and currency == "NGN" and db_provider != "cbn_nfem":
                logger.warning(
                    "strict_ngn_ignoring_non_official_db_rate",
                    provider=db_provider,
                )
            else:
                self._write_l1_rate(currency, db_rate, db_provider)
                await self._write_redis_rate(currency, db_rate, db_provider)
                return db_rate

        # Live fetch
        try:
            live_rate, provider = await self._fetch_live_rate(currency)
            if strict and currency == "NGN" and provider != "cbn_nfem":
                raise ExchangeRateUnavailableError(
                    "Official NGN rate unavailable; charging halted"
                )
            self._write_l1_rate(currency, live_rate, provider)
            await self._write_redis_rate(currency, live_rate, provider)
            # Keep DB authoritative for NGN official rates only.
            if not (currency == "NGN" and provider != "cbn_nfem"):
                await self._upsert_db_rate(currency, live_rate, provider)
            return live_rate
        except ExchangeRateUnavailableError:
            raise
        except Exception as exc:
            logger.warning(
                "exchange_rate_live_fetch_failed",
                currency=currency,
                strict=strict,
                error=str(exc),
            )

        # Degraded path
        if db_rate is not None and not strict:
            logger.warning(
                "exchange_rate_using_stale_db_rate",
                currency=currency,
                provider=db_provider or "unknown",
                updated_at=db_updated_at.isoformat() if db_updated_at else None,
            )
            self._write_l1_rate(currency, db_rate, db_provider)
            return db_rate

        if strict:
            if db_rate is not None:
                raise ExchangeRateUnavailableError(
                    f"{currency} rate is stale and live refresh failed"
                )
            raise ExchangeRateUnavailableError(f"{currency} rate is unavailable")

        # Non-strict final fallback for non-billing contexts.
        return Decimal("1.0")

    async def get_ngn_rate(self, *, strict: bool = True) -> float:
        return float(await self.get_rate("NGN", strict=strict))

    @staticmethod
    def convert_usd_to_ngn(usd_amount: float | Decimal, rate: float | Decimal) -> int:
        """
        Convert USD to NGN subunits (kobo).
        Paystack expects integer subunits.
        """
        ngn_amount = Decimal(str(usd_amount)) * Decimal(str(rate))
        return int(
            (ngn_amount * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP)
        )

    async def list_cached_rates(self) -> dict[str, Decimal]:
        """
        Return cached USD base rates from DB cache with in-memory fallback.
        """
        rates: dict[str, Decimal] = {"USD": Decimal("1.0")}
        try:
            async with self._session_scope() as session:
                result = await session.execute(
                    select(ExchangeRate).where(ExchangeRate.from_currency == "USD")
                )
                rows = result.scalars().all()
                for row in rows:
                    code = str(row.to_currency or "").strip().upper()
                    if not code:
                        continue
                    try:
                        rates[code] = Decimal(str(row.rate))
                    except Exception:
                        continue
        except Exception as exc:
            logger.warning("exchange_rate_list_cached_failed", error=str(exc))

        for code, payload in _RATES_CACHE.items():
            raw_rate: Any = payload[0] if isinstance(payload, tuple) and payload else None
            if isinstance(raw_rate, Decimal):
                rates[str(code).upper()] = raw_rate

        return rates


async def get_exchange_rate(to_currency: str, *, strict: bool = False) -> Decimal:
    """Convenience function for existing call sites."""
    service = ExchangeRateService()
    return await service.get_rate(to_currency, strict=strict)


async def list_exchange_rates() -> dict[str, Decimal]:
    """Return cached exchange rates for diagnostics and internal APIs."""
    service = ExchangeRateService()
    return await service.list_cached_rates()


async def convert_usd(
    amount_usd: float | Decimal,
    to_currency: str,
    *,
    strict: bool = False,
) -> Decimal:
    """Convert USD amount to target currency."""
    currency = (to_currency or "USD").upper()
    if currency == "USD":
        return Decimal(str(amount_usd))
    rate = await get_exchange_rate(currency, strict=strict)
    return Decimal(str(amount_usd)) * rate


async def convert_to_usd(
    amount: float | Decimal,
    from_currency: str,
    *,
    strict: bool = False,
) -> Decimal:
    """Convert amount from source currency into USD."""
    currency = (from_currency or "USD").upper()
    amount_dec = Decimal(str(amount))
    if currency == "USD":
        return amount_dec
    rate = await get_exchange_rate(currency, strict=strict)
    if rate <= 0:
        return amount_dec
    return amount_dec / rate


async def format_currency(
    amount_usd: float | Decimal,
    to_currency: str,
    *,
    strict: bool = False,
) -> str:
    """Format USD-denominated value in the requested currency."""
    converted = await convert_usd(amount_usd, to_currency, strict=strict)
    currency = (to_currency or "USD").upper()

    symbols = {"NGN": "₦", "USD": "$", "EUR": "€", "GBP": "£"}
    symbol = symbols.get(currency, f"{currency} ")
    return f"{symbol}{float(converted):,.2f}"
