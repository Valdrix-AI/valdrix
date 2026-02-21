"""
Tests for the unified ExchangeRateService used by billing and reporting.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.core.currency import (
    ExchangeRateService,
    ExchangeRateUnavailableError,
    _RATES_CACHE,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture(autouse=True)
def clear_cache():
    _RATES_CACHE.clear()
    _RATES_CACHE["USD"] = (Decimal("1.0"), time.time(), "internal")
    yield


def _db_row(rate: float, *, updated: datetime, provider: str = "cbn_nfem") -> MagicMock:
    row = MagicMock()
    row.rate = rate
    row.last_updated = updated
    row.provider = provider
    return row


@pytest.mark.asyncio
async def test_get_ngn_rate_uses_fresh_db_cache(mock_db):
    row = _db_row(1500.0, updated=datetime.now(timezone.utc) - timedelta(hours=1))
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(service, "_fetch_live_rate", new=AsyncMock()) as mock_fetch:
        rate = await service.get_ngn_rate(strict=True)
    assert rate == 1500.0
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_ngn_rate_stale_cache_fetches_live(mock_db):
    row = _db_row(1400.0, updated=datetime.now(timezone.utc) - timedelta(hours=48))
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with (
        patch.object(
            service,
            "_fetch_live_rate",
            new=AsyncMock(return_value=(Decimal("1550.0"), "cbn_nfem")),
        ) as mock_fetch,
        patch.object(service, "_upsert_db_rate", new=AsyncMock()),
    ):
        rate = await service.get_ngn_rate(strict=True)
    assert rate == 1550.0
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_ngn_rate_no_data_raises_in_strict_mode(mock_db):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(
        service,
        "_fetch_live_rate",
        new=AsyncMock(side_effect=RuntimeError("provider down")),
    ):
        with pytest.raises(ExchangeRateUnavailableError, match="unavailable"):
            await service.get_ngn_rate(strict=True)


@pytest.mark.asyncio
async def test_get_ngn_rate_stale_data_raises_when_live_fails(mock_db):
    row = _db_row(1400.0, updated=datetime.now(timezone.utc) - timedelta(hours=48))
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(
        service,
        "_fetch_live_rate",
        new=AsyncMock(side_effect=RuntimeError("provider down")),
    ):
        with pytest.raises(ExchangeRateUnavailableError, match="stale"):
            await service.get_ngn_rate(strict=True)


@pytest.mark.asyncio
async def test_get_ngn_rate_stale_data_allowed_non_strict(mock_db):
    row = _db_row(1400.0, updated=datetime.now(timezone.utc) - timedelta(hours=48))
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(
        service,
        "_fetch_live_rate",
        new=AsyncMock(side_effect=RuntimeError("provider down")),
    ):
        rate = await service.get_rate("NGN", strict=False)
    assert rate == Decimal("1400.0")


@pytest.mark.asyncio
async def test_get_ngn_rate_strict_ignores_fresh_non_cbn_db_rate(mock_db):
    row = _db_row(
        1400.0,
        updated=datetime.now(timezone.utc) - timedelta(hours=1),
        provider="open_er_api",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(
        service,
        "_fetch_live_rate",
        new=AsyncMock(side_effect=RuntimeError("provider down")),
    ) as mock_fetch:
        with pytest.raises(ExchangeRateUnavailableError, match="stale"):
            await service.get_ngn_rate(strict=True)
    mock_fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_ngn_rate_rejects_non_cbn_provider_in_strict_mode(mock_db):
    row = _db_row(1400.0, updated=datetime.now(timezone.utc) - timedelta(hours=48))
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = result

    service = ExchangeRateService(mock_db)
    with patch.object(
        service,
        "_fetch_live_rate",
        new=AsyncMock(return_value=(Decimal("1600.0"), "open_er_api")),
    ):
        with pytest.raises(ExchangeRateUnavailableError, match="Official NGN"):
            await service.get_ngn_rate(strict=True)


@pytest.mark.asyncio
async def test_upsert_db_rate_rolls_back_on_commit_failure(mock_db):
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result
    mock_db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))

    service = ExchangeRateService(mock_db)
    await service._upsert_db_rate("NGN", Decimal("1500.0"), "cbn_nfem")
    mock_db.rollback.assert_called_once()


def test_convert_usd_to_ngn():
    service = ExchangeRateService(MagicMock())
    assert service.convert_usd_to_ngn(10.0, 1500.0) == 1500000
    assert service.convert_usd_to_ngn(0.50, 1500.0) == 75000
