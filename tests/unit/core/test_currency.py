import pytest
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.shared.core.currency import (
    ExchangeRateService,
    _RATES_CACHE,
    convert_usd,
    format_currency,
    get_exchange_rate,
)


@pytest.fixture(autouse=True)
def clear_cache():
    _RATES_CACHE.clear()
    _RATES_CACHE["USD"] = (Decimal("1.0"), time.time())
    with patch("app.shared.core.cache.get_cache_service") as mock_cache_cls:
        mock_cache_cls.return_value.enabled = False
        yield


@pytest.mark.asyncio
async def test_convert_usd_to_ngn_from_cbn_success():
    """NGN conversion should use CBN NFEM data when available."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [
        {
            "ratedate": "February-18-2026",
            "weightedAvgRate": "1338.1066",
            "closingrate": "1340.0000",
        }
    ]
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.shared.core.http.get_http_client", return_value=mock_client):
        rate = await get_exchange_rate("NGN")
        assert rate == Decimal("1338.1066")

        amount_ngn = await convert_usd(10, "NGN")
        assert amount_ngn == Decimal("13381.0660")

        formatted = await format_currency(10, "NGN")
        assert "₦13,381.07" in formatted


@pytest.mark.asyncio
async def test_convert_usd_uses_fresh_db_cache_for_non_ngn():
    """Non-NGN currencies should resolve from cached DB rows when available."""
    with patch.object(
        ExchangeRateService,
        "_read_db_rate",
        new=AsyncMock(
            return_value=(Decimal("0.92"), datetime.now(timezone.utc), "manual")
        ),
    ):
        rate = await get_exchange_rate("EUR")
        assert rate == Decimal("0.92")
        amount_eur = await convert_usd(100, "EUR")
        assert amount_eur == Decimal("92.0")


@pytest.mark.asyncio
async def test_convert_usd_to_usd():
    """Test that USD to USD conversion returns the same amount."""
    amount = await convert_usd(123.45, "USD")
    assert amount == Decimal("123.45")

    formatted = await format_currency(123.45, "USD")
    assert "$123.45" in formatted
