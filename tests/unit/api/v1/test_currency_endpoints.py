import pytest
import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.pricing import PricingTier
from app.shared.core.config import Settings


@pytest.mark.asyncio
async def test_get_all_rates(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="rates@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    mock_settings = Settings()
    mock_settings.SUPPORTED_CURRENCIES = ["USD", "NGN"]

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.currency.get_settings",
                return_value=mock_settings,
            ),
            patch(
                "app.modules.reporting.api.v1.currency.get_exchange_rate",
                new=AsyncMock(),
            ) as mock_rate,
        ):
            mock_rate.side_effect = [1.0, 1500.0]
            response = await async_client.get("/api/v1/currency/rates")
            assert response.status_code == 200
            data = response.json()
            assert data["USD"] == 1.0
            assert data["NGN"] == 1500.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_convert_currency(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="convert@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.shared.core.currency.convert_usd",
                new=AsyncMock(return_value=1500.0),
            ) as mock_convert,
            patch(
                "app.shared.core.currency.format_currency",
                new=AsyncMock(return_value="₦1,500.00"),
            ) as mock_format,
        ):
            response = await async_client.get(
                "/api/v1/currency/convert", params={"amount": 1.0, "to": "NGN"}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["converted_amount"] == 1500.0
            assert data["target_currency"] == "NGN"
            assert data["formatted"] == "₦1,500.00"
            assert mock_convert.await_count == 1
            assert mock_format.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
