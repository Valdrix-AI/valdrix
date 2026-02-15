"""
Tests for ExchangeRateService - Currency Conversion
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.modules.billing.domain.billing.currency import ExchangeRateService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_get_ngn_rate_from_cache(mock_db):
    """Test get_ngn_rate uses cached rate if fresh."""
    mock_rate = MagicMock()
    mock_rate.rate = 1500.0
    mock_rate.last_updated = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_rate
    mock_db.execute.return_value = mock_result

    with patch("app.modules.billing.domain.billing.currency.settings") as mock_settings:
        mock_settings.EXCHANGERATE_API_KEY = "test-key"
        service = ExchangeRateService(mock_db)
        service.api_key = "test-key"

        rate = await service.get_ngn_rate()

        assert rate == 1500.0


@pytest.mark.asyncio
async def test_get_ngn_rate_stale_cache_fetches_api(mock_db):
    """Test get_ngn_rate fetches from API if cache is stale."""
    mock_rate = MagicMock()
    mock_rate.rate = 1400.0
    mock_rate.last_updated = datetime.now(timezone.utc) - timedelta(hours=48)  # Stale

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_rate
    mock_db.execute.return_value = mock_result

    with patch("app.modules.billing.domain.billing.currency.settings") as mock_settings:
        mock_settings.EXCHANGERATE_API_KEY = "test-key"
        service = ExchangeRateService(mock_db)
        service.api_key = "test-key"

        with patch.object(
            service, "_fetch_from_api", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = 1550.0

            with patch.object(service, "_update_db_cache", new_callable=AsyncMock):
                rate = await service.get_ngn_rate()

                assert rate == 1550.0
                mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_ngn_rate_no_api_key_uses_stale(mock_db):
    """Test get_ngn_rate uses stale cache when no API key."""
    mock_rate = MagicMock()
    mock_rate.rate = 1400.0
    mock_rate.last_updated = datetime.now(timezone.utc) - timedelta(hours=48)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_rate
    mock_db.execute.return_value = mock_result

    with patch("app.modules.billing.domain.billing.currency.settings") as mock_settings:
        mock_settings.EXCHANGERATE_API_KEY = None
        service = ExchangeRateService(mock_db)
        service.api_key = None

        rate = await service.get_ngn_rate()

        assert rate == 1400.0


@pytest.mark.asyncio
async def test_get_ngn_rate_fallback(mock_db):
    """Test get_ngn_rate uses fallback when nothing available."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("app.modules.billing.domain.billing.currency.settings") as mock_settings:
        mock_settings.EXCHANGERATE_API_KEY = None
        mock_settings.FALLBACK_NGN_RATE = 1450.0
        service = ExchangeRateService(mock_db)
        service.api_key = None

        rate = await service.get_ngn_rate()

        assert rate == 1450.0  # Fallback rate


@pytest.mark.asyncio
async def test_get_ngn_rate_db_exception_uses_api(mock_db):
    """DB lookup errors should not block API fetch."""
    mock_db.execute = AsyncMock(side_effect=RuntimeError("db down"))

    with patch("app.modules.billing.domain.billing.currency.settings") as mock_settings:
        mock_settings.EXCHANGERATE_API_KEY = "test-key"
        service = ExchangeRateService(mock_db)
        service.api_key = "test-key"

        with patch.object(
            service, "_fetch_from_api", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = 1600.0
            with patch.object(service, "_update_db_cache", new_callable=AsyncMock):
                rate = await service.get_ngn_rate()
                assert rate == 1600.0


@pytest.mark.asyncio
async def test_get_ngn_rate_api_failure_uses_stale(mock_db):
    """API errors should fall back to stale DB rate when available."""
    stale_rate = MagicMock()
    stale_rate.rate = 1400.0
    stale_rate.last_updated = datetime.now(timezone.utc) - timedelta(hours=48)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = stale_rate
    mock_db.execute.return_value = mock_result

    with (
        patch("app.modules.billing.domain.billing.currency.settings") as mock_settings,
        patch("app.modules.billing.domain.billing.currency.logger") as mock_logger,
    ):
        mock_settings.EXCHANGERATE_API_KEY = "test-key"
        service = ExchangeRateService(mock_db)
        service.api_key = "test-key"

        with patch.object(
            service,
            "_fetch_from_api",
            new_callable=AsyncMock,
            side_effect=RuntimeError("api down"),
        ):
            rate = await service.get_ngn_rate()
            assert rate == 1400.0
            mock_logger.warning.assert_called_once()
            args, kwargs = mock_logger.warning.call_args
            assert args[0] == "currency_using_stale_db_rate"
            assert isinstance(kwargs.get("age"), timedelta)


@pytest.mark.asyncio
async def test_fetch_from_api_error_result(mock_db):
    """API failure response should raise ValueError."""
    service = ExchangeRateService(mock_db)
    service.api_key = "test-key"

    mock_response = MagicMock()
    mock_response.json.return_value = {"result": "error", "error-type": "invalid-key"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ValueError):
            await service._fetch_from_api()


@pytest.mark.asyncio
async def test_update_db_cache_rolls_back_on_failure(mock_db):
    """DB failures during cache update should rollback."""
    mock_db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    service = ExchangeRateService(mock_db)
    await service._update_db_cache(1500.0)
    mock_db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_from_api(mock_db):
    """Test _fetch_from_api parses response correctly."""
    service = ExchangeRateService(mock_db)
    service.api_key = "test-key"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "result": "success",
        "conversion_rates": {"NGN": 1525.0},
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        rate = await service._fetch_from_api()

        assert rate == 1525.0


@pytest.mark.asyncio
async def test_update_db_cache_insert(mock_db):
    """Test _update_db_cache inserts new record."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    service = ExchangeRateService(mock_db)

    await service._update_db_cache(1500.0)

    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_db_cache_update(mock_db):
    """Test _update_db_cache updates existing record."""
    mock_rate = MagicMock()
    mock_rate.rate = 1400.0

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_rate
    mock_db.execute.return_value = mock_result

    service = ExchangeRateService(mock_db)

    await service._update_db_cache(1550.0)

    assert mock_rate.rate == 1550.0
    mock_db.commit.assert_called_once()


def test_convert_usd_to_ngn():
    """Test convert_usd_to_ngn converts correctly to kobo."""
    mock_db = MagicMock()
    service = ExchangeRateService(mock_db)

    # $10 at 1500 NGN = 15000 NGN = 1500000 kobo
    result = service.convert_usd_to_ngn(10.0, 1500.0)
    assert result == 1500000

    # $0.50 at 1500 NGN = 750 NGN = 75000 kobo
    result = service.convert_usd_to_ngn(0.50, 1500.0)
    assert result == 75000
