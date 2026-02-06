import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from app.shared.core.currency import get_exchange_rate, convert_usd, format_currency

@pytest.mark.asyncio
async def test_convert_usd_to_ngn_paystack_success():
    """Test converting USD to NGN using a successful Paystack mock."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": True,
        "data": {"rate": 1500.5}
    }
    
    with patch("app.shared.core.currency.get_settings") as mock_settings:
        # Mock Paystack key to enable API call
        mock_settings.return_value.PAYSTACK_SECRET_KEY = "test-secret-key"
        
        with patch("httpx.AsyncClient.get", return_value=mock_response):
            with patch("app.shared.core.currency._RATES_CACHE", {}): # Clear cache
                rate = await get_exchange_rate("NGN")
                assert rate == Decimal("1500.5")
                
                amount_ngn = await convert_usd(10, "NGN")
                assert amount_ngn == Decimal("15005.0")
                
                formatted = await format_currency(10, "NGN")
                assert "₦15,005.00" in formatted

@pytest.mark.asyncio
async def test_convert_usd_fallback_rates():
    """Test switching to fallback rates if Paystack fails."""
    mock_response = MagicMock()
    mock_response.status_code = 401 # Unauthorized or generic failure
    
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with patch("app.shared.core.currency._RATES_CACHE", {}):
            rate = await get_exchange_rate("EUR")
            # EUR is in FALLBACK_RATES as 0.92
            assert rate == Decimal("0.92")
            
            amount_eur = await convert_usd(100, "EUR")
            assert amount_eur == Decimal("92.00")

@pytest.mark.asyncio
async def test_convert_usd_to_usd():
    """Test that USD to USD conversion returns the same amount."""
    amount = await convert_usd(123.45, "USD")
    assert amount == Decimal("123.45")
    
    formatted = await format_currency(123.45, "USD")
    assert "$123.45" in formatted
