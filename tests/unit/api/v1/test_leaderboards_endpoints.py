import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.pricing import PricingTier
from app.shared.db.session import get_db


@pytest.mark.asyncio
async def test_leaderboard_empty(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="leader@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )

    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = await async_client.get("/api/v1/leaderboards", params={"period": "7d"})
        assert response.status_code == 200
        data = response.json()
        assert data["entries"] == []
        assert data["total_team_savings"] == 0.0
        assert data["period"] == "Last 7 Days"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_leaderboard_populated_all_time(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="leader@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )

    class Row:
        def __init__(self, user_email, total_savings, count):
            self.user_email = user_email
            self.total_savings = total_savings
            self.count = count

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        Row("user1@valdrix.io", 120.5, 3),
        Row("user2@valdrix.io", 50.0, 1),
    ]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = await async_client.get("/api/v1/leaderboards", params={"period": "all"})
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "All Time"
        assert len(data["entries"]) == 2
        assert data["entries"][0]["rank"] == 1
        assert data["entries"][0]["user_email"] == "user1@valdrix.io"
        assert data["total_team_savings"] == 170.5
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
