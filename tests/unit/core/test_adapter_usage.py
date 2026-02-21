from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.shared.core.adapter_usage import fetch_daily_costs_if_supported


class _AsyncAdapter:
    async def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        *,
        group_by_service: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            records=[{"date": str(start_date), "service_grouped": group_by_service}]
        )


class _SyncAdapter:
    def get_daily_costs(
        self,
        start_date: date,
        end_date: date,
        *,
        group_by_service: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            records=[{"date": str(end_date), "service_grouped": group_by_service}]
        )


class _UnsupportedAdapter:
    pass


class _BadSignatureAdapter:
    def get_daily_costs(self, start_date: date, end_date: date) -> dict[str, str]:
        return {"start": str(start_date), "end": str(end_date)}


@pytest.mark.asyncio
async def test_fetch_daily_costs_async_adapter() -> None:
    result = await fetch_daily_costs_if_supported(
        _AsyncAdapter(),
        date(2026, 1, 1),
        date(2026, 1, 2),
        group_by_service=False,
    )
    assert result is not None
    assert result.records[0]["service_grouped"] is False


@pytest.mark.asyncio
async def test_fetch_daily_costs_sync_adapter() -> None:
    result = await fetch_daily_costs_if_supported(
        _SyncAdapter(),
        date(2026, 1, 1),
        date(2026, 1, 2),
    )
    assert result is not None
    assert result.records[0]["service_grouped"] is True


@pytest.mark.asyncio
async def test_fetch_daily_costs_unsupported_adapter_returns_none() -> None:
    result = await fetch_daily_costs_if_supported(
        _UnsupportedAdapter(),
        date(2026, 1, 1),
        date(2026, 1, 2),
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_daily_costs_signature_mismatch_raises() -> None:
    with pytest.raises(TypeError):
        await fetch_daily_costs_if_supported(
            _BadSignatureAdapter(),
            date(2026, 1, 1),
            date(2026, 1, 2),
        )
