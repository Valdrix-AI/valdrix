from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.shared.core.runtime_dependencies import validate_runtime_dependencies


def _settings(
    *,
    environment: str = "development",
    testing: bool = False,
    allow_prophet_fallback: bool = True,
    break_glass_reason: str | None = "Temporary dependency incident",
    break_glass_expires_at: str | None = None,
) -> SimpleNamespace:
    if break_glass_expires_at is None:
        break_glass_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=2)
        ).isoformat()
    return SimpleNamespace(
        ENVIRONMENT=environment,
        TESTING=testing,
        FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=allow_prophet_fallback,
        FORECASTER_BREAK_GLASS_REASON=break_glass_reason,
        FORECASTER_BREAK_GLASS_EXPIRES_AT=break_glass_expires_at,
    )


def test_validate_runtime_dependencies_requires_tiktoken_in_strict_env() -> None:
    settings = _settings(environment="production")

    def available(module_name: str) -> bool:
        return module_name != "tiktoken"

    with patch(
        "app.shared.core.runtime_dependencies._module_available",
        side_effect=available,
    ):
        with pytest.raises(RuntimeError, match="tiktoken"):
            validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_requires_sentry_sdk_when_dsn_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(environment="staging")
    monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.io/1")

    def available(module_name: str) -> bool:
        if module_name == "sentry_sdk":
            return False
        return True

    with patch(
        "app.shared.core.runtime_dependencies._module_available",
        side_effect=available,
    ):
        with pytest.raises(RuntimeError, match="SENTRY_DSN"):
            validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_requires_prophet_when_fallback_disabled() -> None:
    settings = _settings(environment="production", allow_prophet_fallback=False)

    def available(module_name: str) -> bool:
        return module_name != "prophet"

    with patch(
        "app.shared.core.runtime_dependencies._module_available",
        side_effect=available,
    ):
        with pytest.raises(RuntimeError, match="Missing required dependency 'prophet'"):
            validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_logs_prophet_fallback_when_break_glass_enabled() -> None:
    settings = _settings(environment="staging", allow_prophet_fallback=True)

    def available(module_name: str) -> bool:
        return module_name != "prophet"

    with (
        patch(
            "app.shared.core.runtime_dependencies._module_available",
            side_effect=available,
        ),
        patch("app.shared.core.runtime_dependencies.logger") as logger,
    ):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]
        logger.warning.assert_called_once()


def test_validate_runtime_dependencies_rejects_break_glass_without_reason() -> None:
    settings = _settings(
        environment="production",
        allow_prophet_fallback=True,
        break_glass_reason="",
    )

    with pytest.raises(RuntimeError, match="FORECASTER_BREAK_GLASS_REASON"):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_rejects_break_glass_past_expiry() -> None:
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    settings = _settings(
        environment="staging",
        allow_prophet_fallback=True,
        break_glass_expires_at=past,
    )

    with pytest.raises(RuntimeError, match="in the past"):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_rejects_break_glass_invalid_expiry() -> None:
    settings = _settings(
        environment="production",
        allow_prophet_fallback=True,
        break_glass_expires_at="2026-02-20",
    )

    with pytest.raises(RuntimeError, match="ISO-8601"):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]


def test_validate_runtime_dependencies_allows_prophet_fallback_in_dev() -> None:
    settings = _settings(environment="development", allow_prophet_fallback=False)

    def available(module_name: str) -> bool:
        return module_name != "prophet"

    with (
        patch(
            "app.shared.core.runtime_dependencies._module_available",
            side_effect=available,
        ),
        patch("app.shared.core.runtime_dependencies.logger") as logger,
    ):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]
        logger.warning.assert_called_once()


def test_validate_runtime_dependencies_skips_when_testing_enabled() -> None:
    settings = _settings(environment="production", testing=True)

    with patch(
        "app.shared.core.runtime_dependencies._module_available",
        side_effect=AssertionError("should not be called in testing"),
    ):
        validate_runtime_dependencies(settings)  # type: ignore[arg-type]
