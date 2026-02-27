from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.core import rate_limit as rl


def _settings(**overrides):
    base = {
        "REDIS_URL": None,
        "ENVIRONMENT": "development",
        "ALLOW_IN_MEMORY_RATE_LIMITS": False,
        "RATELIMIT_ENABLED": True,
        "TESTING": False,
        "ALLOW_REDIS_IN_TESTS": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _request(*, tenant_id=None, auth_header=None):
    headers = {}
    if auth_header is not None:
        headers["Authorization"] = auth_header
    return SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id), headers=headers)


def test_context_aware_key_falls_back_to_ip_when_hashing_fails() -> None:
    request = _request(auth_header="Bearer abc")
    with (
        patch("app.shared.core.rate_limit.hashlib.sha256", side_effect=RuntimeError("boom")),
        patch("app.shared.core.rate_limit.get_remote_address", return_value="10.0.0.7"),
    ):
        assert rl.context_aware_key(request) == "10.0.0.7"


def test_global_limit_key_sanitizes_namespace_and_defaults_to_global() -> None:
    assert rl.global_limit_key("Enforcement Gate/Prod!")(None) == "global:enforcement_gate_prod_"
    assert rl.global_limit_key("   ")(None) == "global:global"


def test_get_limiter_logs_break_glass_for_production_without_redis() -> None:
    with (
        patch("app.shared.core.rate_limit._limiter", None),
        patch("app.shared.core.rate_limit.get_settings", return_value=_settings(ENVIRONMENT="production", ALLOW_IN_MEMORY_RATE_LIMITS=True)),
        patch("app.shared.core.rate_limit.logger") as logger,
    ):
        limiter = rl.get_limiter()
        assert limiter is not None
        logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_check_remediation_rate_limit_denies_when_production_without_redis() -> None:
    with (
        patch("app.shared.core.rate_limit.get_redis_client", return_value=None),
        patch("app.shared.core.rate_limit.get_settings", return_value=_settings(ENVIRONMENT="production")),
    ):
        allowed = await rl.check_remediation_rate_limit("tenant-1", "stop_instance", limit=5)
        assert allowed is False


@pytest.mark.asyncio
async def test_check_remediation_rate_limit_denies_on_redis_error_in_production() -> None:
    redis = AsyncMock()
    redis.incr.side_effect = RuntimeError("redis down")

    with (
        patch("app.shared.core.rate_limit.get_redis_client", return_value=redis),
        patch("app.shared.core.rate_limit.get_settings", return_value=_settings(ENVIRONMENT="staging")),
    ):
        allowed = await rl.check_remediation_rate_limit("tenant-1", "stop_instance", limit=5)
        assert allowed is False


def test_get_redis_client_returns_none_by_default_in_testing() -> None:
    with patch(
        "app.shared.core.rate_limit.get_settings",
        return_value=_settings(TESTING=True, REDIS_URL="redis://localhost:6379", ALLOW_REDIS_IN_TESTS=False),
    ):
        assert rl.get_redis_client() is None


def test_get_redis_client_recreates_client_when_event_loop_changes() -> None:
    first_client = MagicMock()
    first_client._loop = "old-loop"
    second_client = MagicMock()

    with (
        patch("app.shared.core.rate_limit._redis_client", first_client),
        patch("app.shared.core.rate_limit.get_settings", return_value=_settings(REDIS_URL="redis://localhost:6379")),
        patch("app.shared.core.rate_limit.from_url", side_effect=[second_client]),
        patch("asyncio.get_running_loop", return_value="new-loop"),
    ):
        client = rl.get_redis_client()
        assert client is second_client


def test_analysis_limit_returns_original_function_during_testing() -> None:
    def sample() -> str:
        return "ok"

    with patch("app.shared.core.rate_limit.get_settings", return_value=_settings(TESTING=True)):
        decorated = rl.analysis_limit(sample)
    assert decorated is sample


def test_analysis_limit_delegates_to_limiter_when_not_testing() -> None:
    def sample() -> str:
        return "ok"

    limiter = MagicMock()

    def _decorator(func):
        return lambda: f"decorated:{func()}"

    limiter.limit.return_value = _decorator

    with (
        patch("app.shared.core.rate_limit.get_settings", return_value=_settings(TESTING=False)),
        patch("app.shared.core.rate_limit.get_limiter", return_value=limiter),
    ):
        decorated = rl.analysis_limit(sample)

    limiter.limit.assert_called_once_with(rl.get_analysis_limit)
    assert decorated() == "decorated:ok"


def test_cleanup_stale_remediation_counts_respects_interval_and_prunes() -> None:
    with (
        patch(
            "app.shared.core.rate_limit._remediation_counts",
            {
                "fresh": {"count": 1, "window_start": 9900.0},
                "stale": {"count": 1, "window_start": 1000.0},
            },
        ),
        patch("app.shared.core.rate_limit._remediation_last_cleanup_at", 0.0),
    ):
        rl._cleanup_stale_remediation_counts(10000.0)
        assert "stale" not in rl._remediation_counts
        assert "fresh" in rl._remediation_counts

        # Within cleanup interval; should not remove additional keys.
        rl._remediation_counts["new"] = {"count": 1, "window_start": 1.0}
        rl._cleanup_stale_remediation_counts(10010.0)
        assert "new" in rl._remediation_counts
