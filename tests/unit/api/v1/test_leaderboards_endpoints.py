from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.main import app
from app.modules.reporting.api.v1 import leaderboards as leaderboards_api
from app.shared.core.auth import CurrentUser, UserRole, get_current_user
from app.shared.core.pricing import PricingTier


def _user(
    *, tenant_id: object | None = None, tier: PricingTier = PricingTier.GROWTH
) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id if tenant_id is not None else uuid4(),
        email="leader@valdrics.io",
        role=UserRole.MEMBER,
        tier=tier,
    )


def _result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


class _Cache:
    def __init__(self, *, enabled: bool, cached_payload: object):
        self.enabled = enabled
        self.get = AsyncMock(return_value=cached_payload)
        self.set = AsyncMock(return_value=True)


def test_leaderboard_require_tenant_context_raises() -> None:
    user = CurrentUser(
        id=uuid4(),
        tenant_id=None,
        email="leader-no-tenant@valdrics.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )
    with pytest.raises(HTTPException) as exc:
        leaderboards_api._require_tenant_id(user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Tenant context is required"


@pytest.mark.asyncio
async def test_leaderboard_empty_for_period_7d() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([]))
    cache = _Cache(enabled=False, cached_payload=None)

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="7d",
            current_user=_user(),
            db=db,
        )

    assert payload.entries == []
    assert payload.total_team_savings == 0.0
    assert payload.period == "Last 7 Days"
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_leaderboard_allows_starter_tier() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([]))
    cache = _Cache(enabled=False, cached_payload=None)

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="30d",
            current_user=_user(tier=PricingTier.STARTER),
            db=db,
        )

    assert payload.period == "Last 30 Days"
    assert payload.entries == []
    assert payload.total_team_savings == 0.0


@pytest.mark.asyncio
async def test_leaderboard_populated_all_time_with_mapping_rows() -> None:
    row1 = SimpleNamespace(
        _mapping={
            "user_email": "user1@valdrics.io",
            "total_savings": 120.5,
            "remediation_count": 3,
        }
    )
    row2 = SimpleNamespace(
        _mapping={
            "user_email": "user2@valdrics.io",
            "total_savings": 50.0,
            "remediation_count": 1,
        }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([row1, row2]))
    cache = _Cache(enabled=False, cached_payload=None)

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="all",
            current_user=_user(),
            db=db,
        )

    assert payload.period == "All Time"
    assert len(payload.entries) == 2
    assert payload.entries[0].rank == 1
    assert payload.entries[0].user_email == "user1@valdrics.io"
    assert payload.entries[0].savings_usd == 120.5
    assert payload.entries[0].remediation_count == 3
    assert payload.total_team_savings == 170.5


@pytest.mark.asyncio
async def test_leaderboard_cache_hit_bypasses_db() -> None:
    cached_payload = {
        "period": "Last 30 Days",
        "entries": [
            {
                "rank": 1,
                "user_email": "cached@valdrics.io",
                "savings_usd": 99.0,
                "remediation_count": 2,
            }
        ],
        "total_team_savings": 99.0,
    }
    cache = _Cache(enabled=True, cached_payload=cached_payload)
    db = MagicMock()
    db.execute = AsyncMock()

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="30d",
            current_user=_user(),
            db=db,
        )

    assert payload.total_team_savings == 99.0
    assert payload.entries[0].user_email == "cached@valdrics.io"
    db.execute.assert_not_awaited()
    cache.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_leaderboard_invalid_cache_falls_through_and_sets_cache() -> None:
    row = SimpleNamespace(
        user_email="fallback@valdrics.io",
        total_savings=20.0,
        remediation_count=1,
    )
    cache = _Cache(enabled=True, cached_payload={"entries": "bad-shape"})
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([row]))

    with (
        patch.object(leaderboards_api, "get_cache_service", return_value=cache),
        patch.object(leaderboards_api, "logger") as logger_mock,
    ):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="30d",
            current_user=_user(),
            db=db,
        )

    assert payload.entries[0].user_email == "fallback@valdrics.io"
    assert payload.total_team_savings == 20.0
    logger_mock.warning.assert_called_once()
    cache.set.assert_awaited_once()
    assert cache.set.await_args.kwargs["ttl"] == timedelta(seconds=30)


@pytest.mark.asyncio
async def test_leaderboard_non_dict_cache_payload_falls_through() -> None:
    row = SimpleNamespace(
        user_email="fallback2@valdrics.io",
        total_savings=10.0,
        remediation_count=2,
    )
    cache = _Cache(enabled=True, cached_payload=None)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([row]))

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        payload = await leaderboards_api.get_leaderboard(
            request=object(),
            period="90d",
            current_user=_user(),
            db=db,
        )

    assert payload.period == "Last 90 Days"
    assert payload.total_team_savings == 10.0
    cache.get.assert_awaited_once()
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_leaderboard_replay_is_deterministic_for_same_inputs() -> None:
    row = SimpleNamespace(
        _mapping={
            "user_email": "repeat@valdrics.io",
            "total_savings": 42.5,
            "remediation_count": 2,
        }
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_result([row]))
    cache = _Cache(enabled=False, cached_payload=None)
    current_user = _user(tier=PricingTier.STARTER)

    with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
        first = await leaderboards_api.get_leaderboard(
            request=object(),
            period="30d",
            current_user=current_user,
            db=db,
        )
        second = await leaderboards_api.get_leaderboard(
            request=object(),
            period="30d",
            current_user=current_user,
            db=db,
        )

    assert first.model_dump() == second.model_dump()


@pytest.mark.asyncio
async def test_leaderboard_endpoint_allows_starter_tier(async_client: AsyncClient) -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(tier=PricingTier.STARTER)
    cache = _Cache(enabled=False, cached_payload=None)
    try:
        with patch.object(leaderboards_api, "get_cache_service", return_value=cache):
            response = await async_client.get("/api/v1/leaderboards", params={"period": "30d"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_leaderboard_endpoint_denies_when_feature_gate_fails(
    async_client: AsyncClient,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: _user(tier=PricingTier.STARTER)
    try:
        with patch("app.shared.core.dependencies.is_feature_enabled", return_value=False):
            response = await async_client.get(
                "/api/v1/leaderboards",
                params={"period": "30d"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
