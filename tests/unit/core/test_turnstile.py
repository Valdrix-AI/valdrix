from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.shared.core import turnstile


class _FakeCounter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_FakeCounter":
        self._labels = dict(labels)
        return self

    def inc(self, amount: float = 1.0) -> None:
        self.calls.append((dict(self._labels), float(amount)))


def _settings(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "TURNSTILE_ENABLED": True,
        "TURNSTILE_ENFORCE_IN_TESTING": True,
        "TURNSTILE_SECRET_KEY": "turnstile-secret",
        "TURNSTILE_VERIFY_URL": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        "TURNSTILE_TIMEOUT_SECONDS": 2.0,
        "TURNSTILE_FAIL_OPEN": False,
        "TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT": True,
        "TURNSTILE_REQUIRE_SSO_DISCOVERY": True,
        "TURNSTILE_REQUIRE_ONBOARD": True,
        "TESTING": False,
        "ENVIRONMENT": "test",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _request_with_headers(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
        "client": ("203.0.113.9", 44321),
    }
    return Request(scope)


def test_extract_turnstile_token_header_priority() -> None:
    request = _request_with_headers(
        {
            "CF-Turnstile-Token": "fallback-token",
            "X-Turnstile-Token": "primary-token",
        }
    )
    assert turnstile._extract_turnstile_token(request) == "primary-token"

    only_cf = _request_with_headers({"CF-Turnstile-Token": "cf-only"})
    assert turnstile._extract_turnstile_token(only_cf) == "cf-only"

    assert turnstile._extract_turnstile_token(_request_with_headers()) == ""


def test_should_enforce_branching() -> None:
    metrics = _FakeCounter()
    with patch(
        "app.shared.core.turnstile.TURNSTILE_VERIFICATION_EVENTS_TOTAL",
        metrics,
    ):
        assert (
            turnstile._should_enforce(
                _settings(TURNSTILE_ENABLED=False),
                "public_assessment",
            )
            is False
        )
        assert (
            turnstile._should_enforce(
                _settings(TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT=False),
                "public_assessment",
            )
            is False
        )
        assert (
            turnstile._should_enforce(
                _settings(TESTING=True, TURNSTILE_ENFORCE_IN_TESTING=False),
                "public_assessment",
            )
            is False
        )
        assert (
            turnstile._should_enforce(
                _settings(TESTING=True, TURNSTILE_ENFORCE_IN_TESTING=True),
                "public_assessment",
            )
            is True
        )

    outcomes = {labels["outcome"] for labels, _ in metrics.calls}
    assert "skipped_disabled" in outcomes
    assert "skipped_surface_not_required" in outcomes
    assert "skipped_testing" in outcomes


@pytest.mark.asyncio
async def test_verify_turnstile_with_cloudflare_sets_default_action() -> None:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {"success": True}
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.shared.core.turnstile.get_settings", return_value=_settings()),
        patch("app.shared.core.turnstile.get_http_client", return_value=client),
    ):
        payload = await turnstile._verify_turnstile_with_cloudflare(
            token="abc",
            remote_ip="198.51.100.20",
            surface="onboard",
        )

    assert payload["success"] is True
    assert payload["action"] == "onboard"
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_verify_turnstile_with_cloudflare_handles_non_dict_payload() -> None:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = ["unexpected", "payload"]
    client = MagicMock()
    client.post = AsyncMock(return_value=response)

    with (
        patch("app.shared.core.turnstile.get_settings", return_value=_settings()),
        patch("app.shared.core.turnstile.get_http_client", return_value=client),
    ):
        payload = await turnstile._verify_turnstile_with_cloudflare(
            token="abc",
            remote_ip="",
            surface="public_assessment",
        )

    assert payload == {}


@pytest.mark.asyncio
async def test_enforce_turnstile_missing_secret_nonprod_skips() -> None:
    metrics = _FakeCounter()
    with (
        patch(
            "app.shared.core.turnstile.get_settings",
            return_value=_settings(TURNSTILE_SECRET_KEY="", ENVIRONMENT="development"),
        ),
        patch(
            "app.shared.core.turnstile.TURNSTILE_VERIFICATION_EVENTS_TOTAL",
            metrics,
        ),
    ):
        await turnstile._enforce_turnstile_for_surface(
            _request_with_headers(), "public_assessment"
        )

    assert any(
        labels["outcome"] == "skipped_missing_secret_nonprod"
        for labels, _ in metrics.calls
    )


@pytest.mark.asyncio
async def test_enforce_turnstile_missing_secret_staging_rejects() -> None:
    with patch(
        "app.shared.core.turnstile.get_settings",
        return_value=_settings(TURNSTILE_SECRET_KEY="", ENVIRONMENT="staging"),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await turnstile._enforce_turnstile_for_surface(
                _request_with_headers(), "public_assessment"
            )
    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == "turnstile_secret_key_not_configured"


@pytest.mark.asyncio
async def test_enforce_turnstile_missing_token_rejects() -> None:
    with patch(
        "app.shared.core.turnstile.get_settings",
        return_value=_settings(),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await turnstile._enforce_turnstile_for_surface(
                _request_with_headers(), "public_assessment"
            )
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "turnstile_token_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fail_open", "expected_status"),
    [
        (False, 503),
        (True, None),
    ],
)
async def test_enforce_turnstile_verification_unavailable_modes(
    fail_open: bool, expected_status: int | None
) -> None:
    with (
        patch(
            "app.shared.core.turnstile.get_settings",
            return_value=_settings(TURNSTILE_FAIL_OPEN=fail_open),
        ),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("timeout"),
        ),
    ):
        if expected_status is None:
            await turnstile._enforce_turnstile_for_surface(
                _request_with_headers({"X-Turnstile-Token": "token"}),
                "public_assessment",
            )
        else:
            with pytest.raises(HTTPException) as excinfo:
                await turnstile._enforce_turnstile_for_surface(
                    _request_with_headers({"X-Turnstile-Token": "token"}),
                    "public_assessment",
                )
            assert excinfo.value.status_code == expected_status
            assert excinfo.value.detail == "turnstile_verification_unavailable"


@pytest.mark.asyncio
async def test_enforce_turnstile_verification_failed_rejects() -> None:
    with (
        patch("app.shared.core.turnstile.get_settings", return_value=_settings()),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            return_value={"success": False},
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await turnstile._enforce_turnstile_for_surface(
                _request_with_headers({"X-Turnstile-Token": "token"}),
                "public_assessment",
            )
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "turnstile_verification_failed"


@pytest.mark.asyncio
async def test_enforce_turnstile_action_mismatch_rejects() -> None:
    with (
        patch("app.shared.core.turnstile.get_settings", return_value=_settings()),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            return_value={"success": True, "action": "sso_discovery"},
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await turnstile._enforce_turnstile_for_surface(
                _request_with_headers({"X-Turnstile-Token": "token"}),
                "public_assessment",
            )
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "turnstile_action_mismatch"


@pytest.mark.asyncio
async def test_enforce_turnstile_verified_success() -> None:
    with (
        patch("app.shared.core.turnstile.get_settings", return_value=_settings()),
        patch(
            "app.shared.core.turnstile._verify_turnstile_with_cloudflare",
            new_callable=AsyncMock,
            return_value={"success": True, "action": "public_assessment"},
        ),
    ):
        await turnstile._enforce_turnstile_for_surface(
            _request_with_headers({"X-Turnstile-Token": "token"}),
            "public_assessment",
        )
