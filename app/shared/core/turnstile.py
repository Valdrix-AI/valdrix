from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx
import structlog
from fastapi import HTTPException, Request
from slowapi.util import get_remote_address

from app.shared.core.config import ENV_PRODUCTION, ENV_STAGING, get_settings
from app.shared.core.http import get_http_client
from app.shared.core.ops_metrics import TURNSTILE_VERIFICATION_EVENTS_TOTAL

logger = structlog.get_logger()

_SURFACE_PUBLIC_ASSESSMENT = "public_assessment"
_SURFACE_SSO_DISCOVERY = "sso_discovery"
_SURFACE_ONBOARD = "onboard"
_TURNSTILE_TOKEN_HEADERS = ("x-turnstile-token", "cf-turnstile-token")


def _surface_required(settings: Any, surface: str) -> bool:
    if surface == _SURFACE_PUBLIC_ASSESSMENT:
        return bool(getattr(settings, "TURNSTILE_REQUIRE_PUBLIC_ASSESSMENT", False))
    if surface == _SURFACE_SSO_DISCOVERY:
        return bool(getattr(settings, "TURNSTILE_REQUIRE_SSO_DISCOVERY", False))
    if surface == _SURFACE_ONBOARD:
        return bool(getattr(settings, "TURNSTILE_REQUIRE_ONBOARD", False))
    return False


def _should_enforce(settings: Any, surface: str) -> bool:
    if not bool(getattr(settings, "TURNSTILE_ENABLED", False)):
        TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
            surface=surface, outcome="skipped_disabled"
        ).inc()
        return False
    if not _surface_required(settings, surface):
        TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
            surface=surface, outcome="skipped_surface_not_required"
        ).inc()
        return False
    if bool(getattr(settings, "TESTING", False)) and not bool(
        getattr(settings, "TURNSTILE_ENFORCE_IN_TESTING", False)
    ):
        TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
            surface=surface, outcome="skipped_testing"
        ).inc()
        return False
    return True


def _reject(surface: str, status_code: int, detail: str, outcome: str) -> None:
    TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(surface=surface, outcome=outcome).inc()
    raise HTTPException(status_code=status_code, detail=detail)


def _extract_turnstile_token(request: Request) -> str:
    for header_name in _TURNSTILE_TOKEN_HEADERS:
        value = str(request.headers.get(header_name, "") or "").strip()
        if value:
            return value
    return ""


async def _verify_turnstile_with_cloudflare(
    *,
    token: str,
    remote_ip: str,
    surface: str,
) -> Mapping[str, Any]:
    settings = get_settings()
    verify_url = str(
        getattr(
            settings,
            "TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        )
    ).strip()
    secret = str(getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    payload: dict[str, str] = {
        "secret": secret,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    client = get_http_client()
    response = await client.post(
        verify_url,
        data=payload,
        timeout=float(getattr(settings, "TURNSTILE_TIMEOUT_SECONDS", 3.0)),
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, Any] = dict(data)
    if "action" not in normalized:
        # Keep deterministic action checks even when the client omits action.
        normalized["action"] = surface
    return normalized


async def _enforce_turnstile_for_surface(request: Request, surface: str) -> None:
    settings = get_settings()
    if not _should_enforce(settings, surface):
        return

    secret = str(getattr(settings, "TURNSTILE_SECRET_KEY", "") or "").strip()
    if not secret:
        env = str(getattr(settings, "ENVIRONMENT", "") or "").strip().lower()
        if env in {ENV_PRODUCTION, ENV_STAGING}:
            _reject(
                surface,
                status_code=503,
                detail="turnstile_secret_key_not_configured",
                outcome="misconfigured_secret",
            )
        TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
            surface=surface, outcome="skipped_missing_secret_nonprod"
        ).inc()
        logger.warning(
            "turnstile_secret_missing_non_production",
            surface=surface,
            environment=env,
        )
        return

    token = _extract_turnstile_token(request)
    if not token:
        _reject(
            surface,
            status_code=400,
            detail="turnstile_token_required",
            outcome="token_missing",
        )

    remote_ip = str(get_remote_address(request) or "").strip()
    try:
        verify_payload = await _verify_turnstile_with_cloudflare(
            token=token,
            remote_ip=remote_ip,
            surface=surface,
        )
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.warning(
            "turnstile_verification_unavailable",
            surface=surface,
            error=str(exc),
        )
        if bool(getattr(settings, "TURNSTILE_FAIL_OPEN", False)):
            TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
                surface=surface, outcome="verification_unavailable_fail_open"
            ).inc()
            return
        _reject(
            surface,
            status_code=503,
            detail="turnstile_verification_unavailable",
            outcome="verification_unavailable",
        )

    if not bool(verify_payload.get("success", False)):
        _reject(
            surface,
            status_code=403,
            detail="turnstile_verification_failed",
            outcome="verification_failed",
        )

    action = str(verify_payload.get("action", "") or "").strip().lower()
    if action and action != surface:
        _reject(
            surface,
            status_code=403,
            detail="turnstile_action_mismatch",
            outcome="action_mismatch",
        )

    TURNSTILE_VERIFICATION_EVENTS_TOTAL.labels(
        surface=surface, outcome="verified"
    ).inc()


async def require_turnstile_for_public_assessment(request: Request) -> None:
    await _enforce_turnstile_for_surface(request, _SURFACE_PUBLIC_ASSESSMENT)


async def require_turnstile_for_sso_discovery(request: Request) -> None:
    await _enforce_turnstile_for_surface(request, _SURFACE_SSO_DISCOVERY)


async def require_turnstile_for_onboard(request: Request) -> None:
    await _enforce_turnstile_for_surface(request, _SURFACE_ONBOARD)


__all__ = [
    "require_turnstile_for_public_assessment",
    "require_turnstile_for_sso_discovery",
    "require_turnstile_for_onboard",
    "_verify_turnstile_with_cloudflare",
]
