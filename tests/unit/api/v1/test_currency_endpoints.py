from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.api.v1 import currency as currency_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="currency@valdrics.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )


@pytest.mark.asyncio
async def test_get_all_rates_uses_supported_currencies() -> None:
    settings = SimpleNamespace(SUPPORTED_CURRENCIES=["USD", "NGN", "EUR"])
    with (
        patch.object(currency_api, "get_settings", return_value=settings),
        patch.object(
            currency_api,
            "get_exchange_rate",
            new=AsyncMock(side_effect=[1.0, 1500.0, 0.93]),
        ) as rate_mock,
    ):
        response = await currency_api.get_all_rates(current_user=_user())

    assert response == {"USD": 1.0, "NGN": 1500.0, "EUR": 0.93}
    assert rate_mock.await_count == 3


@pytest.mark.asyncio
async def test_convert_currency_formats_and_uppercases_target() -> None:
    with (
        patch(
            "app.shared.core.currency.convert_usd",
            new=AsyncMock(return_value=1500.0),
        ) as convert_mock,
        patch(
            "app.shared.core.currency.format_currency",
            new=AsyncMock(return_value="₦1,500.00"),
        ) as format_mock,
    ):
        response = await currency_api.convert_currency(
            amount=1.0,
            to="ngn",
            current_user=_user(),
        )

    assert response["original_amount_usd"] == 1.0
    assert response["converted_amount"] == 1500.0
    assert response["target_currency"] == "NGN"
    assert response["formatted"] == "₦1,500.00"
    convert_mock.assert_awaited_once_with(1.0, "ngn")
    format_mock.assert_awaited_once_with(1.0, "ngn")
