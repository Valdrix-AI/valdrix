import pytest
import time
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from app.shared.core.currency import (
    get_exchange_rate,
    convert_usd,
    format_currency,
    fetch_paystack_ngn_rate,
    fetch_public_exchange_rates,
    fetch_fallback_rates,
    _RATES_CACHE,
    FALLBACK_RATES
)

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear memory cache and disable redis cache before each test."""
    _RATES_CACHE.clear()
    _RATES_CACHE["USD"] = (Decimal("1.0"), time.time())
    with patch("app.shared.core.cache.get_cache_service") as mock_cache_cls:
        mock_cache_cls.return_value.enabled = False
        yield

class TestCurrencyDeep:
    """Deep tests for currency module to reach 100% coverage."""

    @pytest.mark.asyncio
    async def test_fetch_paystack_no_key(self):
        """Test Paystack fetch without API key."""
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = None
            rate = await fetch_paystack_ngn_rate()
            assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_paystack_error_response(self, respx_mock):
        """Test Paystack fetch with error response."""
        respx_mock.get("https://api.paystack.co/transfer/rate?from=USD&to=NGN").respond(400)
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = "sk_test"
            rate = await fetch_paystack_ngn_rate()
            assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_paystack_invalid_data(self, respx_mock):
        """Test Paystack fetch with invalid JSON data."""
        respx_mock.get("https://api.paystack.co/transfer/rate?from=USD&to=NGN").respond(200, json={"status": True, "data": {}})
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = "sk_test"
            rate = await fetch_paystack_ngn_rate()
            assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_public_rates_failure(self, respx_mock):
        """Test public rate fetch failure."""
        respx_mock.get("https://open.er-api.com/v6/latest/USD").respond(500)
        rates = await fetch_public_exchange_rates()
        assert rates == {}

    @pytest.mark.asyncio
    async def test_fetch_fallback_rates_with_public(self):
        """Test fallback rates when public rates work."""
        with patch("app.shared.core.currency.fetch_public_exchange_rates", AsyncMock(return_value={"EUR": Decimal("0.95")})) :
            rates = await fetch_fallback_rates()
            assert rates["EUR"] == Decimal("0.95")
            assert rates["NGN"] == FALLBACK_RATES["NGN"]

    @pytest.mark.asyncio
    async def test_get_exchange_rate_cached_l1(self):
        """Test L1 (memory) cache hit."""
        _RATES_CACHE["EUR"] = (Decimal("0.90"), time.time())
        rate = await get_exchange_rate("EUR")
        assert rate == Decimal("0.90")

    @pytest.mark.asyncio
    async def test_get_exchange_rate_redis_hit(self):
        """Test L2 (Redis) cache hit."""
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache._get = AsyncMock(return_value={"rate": 1500.0})
        
        with patch("app.shared.core.cache.get_cache_service", return_value=mock_cache):

            rate = await get_exchange_rate("NGN")
            assert rate == Decimal("1500.0")
            assert "NGN" in _RATES_CACHE

    @pytest.mark.asyncio
    async def test_get_exchange_rate_total_failure_returns_one(self):
        """Test fallback to 1.0 when all sources fail."""
        with patch("app.shared.core.currency.fetch_paystack_ngn_rate", AsyncMock(return_value=None)), \
             patch("app.shared.core.currency.fetch_fallback_rates", AsyncMock(return_value={})):
            rate = await get_exchange_rate("UNKNOWN")
            assert rate == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_convert_usd_simple(self):
        """Test simple conversion."""
        with patch("app.shared.core.currency.get_exchange_rate", AsyncMock(return_value=Decimal("1500.0"))):
            converted = await convert_usd(10.0, "NGN")
            assert converted == Decimal("15000.0")

    @pytest.mark.asyncio
    async def test_format_currency_variants(self):
        """Test currency formatting for different symbols."""
        with patch("app.shared.core.currency.get_exchange_rate", AsyncMock(return_value=Decimal("1.0"))):
            assert "$" in await format_currency(10, "USD")
            assert "₦" in await format_currency(10, "NGN")
            assert "€" in await format_currency(10, "EUR")
            assert "£" in await format_currency(10, "GBP")
            assert "ZAR" in await format_currency(10, "ZAR")

    @pytest.mark.asyncio
    async def test_fetch_paystack_success(self, respx_mock):
        """Test Paystack fetch success."""
        respx_mock.get("https://api.paystack.co/transfer/rate?from=USD&to=NGN").respond(200, json={"status": True, "data": {"rate": 1500.5}})
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = "sk_test"
            rate = await fetch_paystack_ngn_rate()
            assert rate == Decimal("1500.5")

    @pytest.mark.asyncio
    async def test_fetch_paystack_missing_rate(self, respx_mock):
        """Test Paystack fetch with missing rate in data."""
        respx_mock.get("https://api.paystack.co/transfer/rate?from=USD&to=NGN").respond(200, json={"status": True, "data": {}})
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = "sk_test"
            rate = await fetch_paystack_ngn_rate()
            assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_paystack_exception(self, respx_mock):
        """Test Paystack fetch with exception."""
        respx_mock.get("https://api.paystack.co/transfer/rate?from=USD&to=NGN").side_effect = Exception("Network fail")
        with patch("app.shared.core.currency.get_settings") as mock_settings:
            mock_settings.return_value.PAYSTACK_SECRET_KEY = "sk_test"
            rate = await fetch_paystack_ngn_rate()
            assert rate is None

    @pytest.mark.asyncio
    async def test_fetch_public_rates_success(self, respx_mock):
        """Test public rate fetch success."""
        respx_mock.get("https://open.er-api.com/v6/latest/USD").respond(200, json={"result": "success", "rates": {"EUR": 0.92}})
        rates = await fetch_public_exchange_rates()
        assert rates["EUR"] == Decimal("0.92")

    @pytest.mark.asyncio
    async def test_get_exchange_rate_update_redis(self):
        """Test that get_exchange_rate updates Redis cache."""
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache._get = AsyncMock(return_value=None)
        mock_cache._set = AsyncMock()
        
        with patch("app.shared.core.cache.get_cache_service", return_value=mock_cache), \
             patch("app.shared.core.currency.fetch_paystack_ngn_rate", AsyncMock(return_value=Decimal("1500.0"))):
            rate = await get_exchange_rate("NGN")
            assert rate == Decimal("1500.0")
            assert mock_cache._set.called

