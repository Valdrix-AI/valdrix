from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.optimization.adapters.saas.plugins.api import (
    GitHubUnusedSeatPlugin,
    _coerce_token,
)


class _SecretLike:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _AsyncClientCtx:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        del exc_type, exc_val, exc_tb
        return None


def _response(*, status_code: int, payload: object) -> object:
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def test_coerce_token_handles_none_secretlike_and_whitespace() -> None:
    assert _coerce_token(None) is None
    assert _coerce_token(_SecretLike("  ghp_token  ")) == "ghp_token"
    assert _coerce_token("   ") is None


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_member_filter_and_parse_error_branches() -> None:
    plugin = GitHubUnusedSeatPlugin()

    members = [
        "not-a-dict",
        {"login": "   ", "last_activity": "2025-01-01T00:00:00Z"},
        {"login": "missing-last-active"},
        {"login": "parse-error", "last_activity": "bad-ts"},
        {"login": "recent-naive", "last_activity": "naive"},
        {"login": "stale", "last_activity": "stale"},
    ]

    client = AsyncMock()
    client.get.return_value = _response(status_code=200, payload=members)
    now = datetime.now(timezone.utc)
    parse_map = {
        "naive": (now - timedelta(days=5)).replace(tzinfo=None),
        "stale": now - timedelta(days=45),
    }

    def _parse_timestamp(raw: str) -> datetime:
        if raw == "bad-ts":
            raise ValueError("bad timestamp")
        return parse_map[raw]

    with (
        patch("httpx.AsyncClient", return_value=_AsyncClientCtx(client)),
        patch(
            "app.modules.optimization.adapters.saas.plugins.api.parse_timestamp",
            side_effect=_parse_timestamp,
        ),
    ):
        rows = await plugin.scan(
            session=None,
            region="global",
            credentials={"api_key": _SecretLike(" ghp_x "), "organization": "org-1"},
            config={"unused_threshold_days": "not-int", "seat_cost_usd": "not-float"},
        )

    assert len(rows) == 1
    assert rows[0]["resource_id"] == "stale"
    assert rows[0]["monthly_cost"] == 21.0


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_non_200_logs_warning_and_returns_empty() -> None:
    plugin = GitHubUnusedSeatPlugin()
    client = AsyncMock()
    client.get.return_value = _response(status_code=403, payload={"message": "forbidden"})

    with (
        patch("httpx.AsyncClient", return_value=_AsyncClientCtx(client)),
        patch("app.modules.optimization.adapters.saas.plugins.api.logger.warning") as warning,
    ):
        rows = await plugin.scan(
            session=None,
            region="global",
            credentials={"api_key": "ghp_x"},
            config={"github_org": "my-org"},
        )

    assert rows == []
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_uses_connector_config_fallback() -> None:
    plugin = GitHubUnusedSeatPlugin()
    client = AsyncMock()
    client.get.return_value = _response(status_code=403, payload={"message": "forbidden"})

    with patch("httpx.AsyncClient", return_value=_AsyncClientCtx(client)):
        rows = await plugin.scan(
            session=None,
            region="global",
            credentials={
                "connector_config": {"github_token": "ghp_x", "github_org": "cfg-org"}
            },
            config=None,
        )

    assert rows == []


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_non_list_members_payload_returns_empty() -> None:
    plugin = GitHubUnusedSeatPlugin()
    client = AsyncMock()
    client.get.return_value = _response(status_code=200, payload={"value": "not-a-list"})

    with patch("httpx.AsyncClient", return_value=_AsyncClientCtx(client)):
        rows = await plugin.scan(
            session=None,
            region="global",
            credentials={"api_key": "ghp_x"},
            config={"github_org": "my-org"},
        )

    assert rows == []


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_missing_config_logs_debug() -> None:
    plugin = GitHubUnusedSeatPlugin()

    with patch("app.modules.optimization.adapters.saas.plugins.api.logger.debug") as debug:
        rows = await plugin.scan(session=None, region="global", credentials={}, config={})

    assert rows == []
    debug.assert_called_once()


@pytest.mark.asyncio
async def test_github_unused_seat_plugin_logs_outer_exception() -> None:
    plugin = GitHubUnusedSeatPlugin()

    with (
        patch("httpx.AsyncClient", side_effect=RuntimeError("boom")),
        patch("app.modules.optimization.adapters.saas.plugins.api.logger.error") as error,
    ):
        rows = await plugin.scan(
            session=None,
            region="global",
            credentials={"api_key": "ghp_x"},
            config={"github_org": "my-org"},
        )

    assert rows == []
    error.assert_called_once()
