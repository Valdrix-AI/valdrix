from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()
_ROLE_LOOKUP_LIMIT = 200
_ROLE_LOOKUP_CONCURRENCY = 8


def _coerce_payload_rows(payload: dict[str, Any], fallback_key: str) -> list[dict[str, Any]]:
    rows = payload.get("value", payload.get(fallback_key, []))
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _extract_login_set(rows: list[dict[str, Any]]) -> set[str]:
    logins: set[str] = set()
    for row in rows:
        login = str(row.get("login") or "").strip().lower()
        if login:
            logins.add(login)
    return logins


async def _load_login_set(
    runtime: LicenseVendorRuntime,
    *,
    url: str,
    headers: dict[str, str],
    fallback_key: str,
    log_event: str,
) -> tuple[bool, set[str]]:
    try:
        payload = await runtime._get_json(url, headers=headers)
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.warning(log_event, error=str(exc))
        return False, set()
    rows = _coerce_payload_rows(payload, fallback_key)
    return True, _extract_login_set(rows)


async def _fetch_membership_role(
    runtime: LicenseVendorRuntime,
    *,
    org: str,
    login: str,
    headers: dict[str, str],
) -> tuple[str, str | None, str | None]:
    url = f"https://api.github.com/orgs/{org}/memberships/{login}"
    try:
        payload = await runtime._get_json(url, headers=headers)
    except (ExternalAPIError, httpx.HTTPError):
        return login, None, None

    role_raw = payload.get("role")
    role = str(role_raw).strip().lower() if isinstance(role_raw, str) else None
    state_raw = payload.get("state")
    state = str(state_raw).strip().lower() if isinstance(state_raw, str) else None
    return login, role, state


async def revoke_github(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    token = runtime._resolve_api_key()
    org = runtime._connector_config.get("github_org")
    if not org:
        logger.warning("github_revoke_failed_no_org", user_id=resource_id)
        return False

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/orgs/{org}/memberships/{resource_id}"

    try:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.delete(url, headers=headers)

        if response.status_code == 204:
            logger.info("github_membership_revoked", user_id=resource_id, org=org)
            return True

        logger.warning(
            "github_membership_revoke_failed",
            user_id=resource_id,
            status=response.status_code,
        )
        return False
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("github_membership_revoke_error", user_id=resource_id, error=str(exc))
        return False


async def list_github_activity(
    runtime: LicenseVendorRuntime,
    *,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    org = runtime._connector_config.get("github_org")
    if not org:
        return []

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        members_url = f"https://api.github.com/orgs/{org}/members"
        members_payload = await runtime._get_json(members_url, headers=headers)
        members = _coerce_payload_rows(members_payload, "members")

        events_url = f"https://api.github.com/orgs/{org}/events?per_page=100"
        events_payload = await runtime._get_json(events_url, headers=headers)
        events = _coerce_payload_rows(events_payload, "events")

        _, admin_logins = await _load_login_set(
            runtime,
            url=f"https://api.github.com/orgs/{org}/members?role=admin&per_page=100",
            headers=headers,
            fallback_key="members",
            log_event="github_list_admin_members_failed",
        )
        mfa_visibility, two_factor_disabled_logins = await _load_login_set(
            runtime,
            url=f"https://api.github.com/orgs/{org}/members?filter=2fa_disabled&per_page=100",
            headers=headers,
            fallback_key="members",
            log_event="github_list_two_factor_status_failed",
        )

        last_event_per_user: dict[str, datetime] = {}
        for event in events:
            actor = event.get("actor")
            login = actor.get("login") if isinstance(actor, dict) else None
            created_at = event.get("created_at")
            if login and created_at:
                normalized_login = str(login).strip().lower()
                if not normalized_login:
                    continue
                try:
                    ts = parse_timestamp_fn(created_at)
                except (ValueError, TypeError):
                    continue
                if (
                    normalized_login not in last_event_per_user
                    or ts > last_event_per_user[normalized_login]
                ):
                    last_event_per_user[normalized_login] = ts

        role_by_login: dict[str, str] = {}
        membership_state_by_login: dict[str, str] = {}
        logins_for_role_lookup = []
        for member in members:
            login = str(member.get("login") or "").strip().lower()
            if login:
                logins_for_role_lookup.append(login)

        limited_logins = logins_for_role_lookup[:_ROLE_LOOKUP_LIMIT]
        if len(logins_for_role_lookup) > len(limited_logins):
            logger.warning(
                "github_membership_role_lookup_truncated",
                total_members=len(logins_for_role_lookup),
                looked_up=len(limited_logins),
            )
        if limited_logins:
            semaphore = asyncio.Semaphore(_ROLE_LOOKUP_CONCURRENCY)

            async def _bounded_role_lookup(login: str) -> tuple[str, str | None, str | None]:
                async with semaphore:
                    return await _fetch_membership_role(
                        runtime,
                        org=org,
                        login=login,
                        headers=headers,
                    )

            role_results = await asyncio.gather(
                *(_bounded_role_lookup(login) for login in limited_logins)
            )
            for login, role, state in role_results:
                if role:
                    role_by_login[login] = role
                if state:
                    membership_state_by_login[login] = state

        activity_records = []
        for member in members:
            login = str(member.get("login") or "").strip().lower()
            if not login:
                continue
            explicit_role = role_by_login.get(login)
            is_admin = (
                bool(member.get("site_admin"))
                or login in admin_logins
                or explicit_role == "admin"
            )
            org_role = explicit_role or ("admin" if is_admin else "member")
            mfa_enabled: bool | None = None
            if mfa_visibility:
                mfa_enabled = login not in two_factor_disabled_logins
            activity_records.append(
                {
                    "user_id": login,
                    "email": login,
                    "full_name": member.get("name") or login,
                    "last_active_at": last_event_per_user.get(login),
                    "is_admin": is_admin,
                    "org_role": org_role,
                    "membership_state": membership_state_by_login.get(login),
                    "mfa_enabled": mfa_enabled,
                    "two_factor_authentication": mfa_enabled,
                    "mfa_signal_source": "org_members_filter" if mfa_visibility else None,
                    "suspended": False,
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("github_list_members_failed", error=str(exc))
        return []
