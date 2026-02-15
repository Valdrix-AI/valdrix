import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
        response = await async_client.get(
            "/api/v1/leaderboards", params={"period": "7d"}
        )
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
        response = await async_client.get(
            "/api/v1/leaderboards", params={"period": "all"}
        )
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


@pytest.mark.asyncio
async def test_leaderboard_requires_tenant_context(async_client: AsyncClient, app):
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=None,
        email="leader-no-tenant@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )
    mock_db = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = await async_client.get(
            "/api/v1/leaderboards", params={"period": "7d"}
        )
        assert response.status_code == 403
        payload = response.json()
        message = (payload.get("error") or payload.get("detail") or "").lower()
        assert "tenant context" in message
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_leaderboard_cache_hit_bypasses_db(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="leader-cache@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )
    mock_db = AsyncMock()

    cached_payload = {
        "period": "Last 30 Days",
        "entries": [
            {
                "rank": 1,
                "user_email": "cached@valdrix.io",
                "savings_usd": 99.0,
                "remediation_count": 2,
            }
        ],
        "total_team_savings": 99.0,
    }

    class CacheHit:
        enabled = True

        async def get(self, _key: str):
            return cached_payload

        async def set(self, _key: str, _value, ttl=None):
            return True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        with patch(
            "app.modules.reporting.api.v1.leaderboards.get_cache_service",
            return_value=CacheHit(),
        ):
            response = await async_client.get(
                "/api/v1/leaderboards", params={"period": "30d"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["total_team_savings"] == 99.0
        assert data["entries"][0]["user_email"] == "cached@valdrix.io"
        mock_db.execute.assert_not_awaited()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)
