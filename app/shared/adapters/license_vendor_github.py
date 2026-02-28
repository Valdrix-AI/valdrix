from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


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
        members = members_payload.get("value", members_payload.get("members", []))
        if not isinstance(members, list):
            members = []

        events_url = f"https://api.github.com/orgs/{org}/events?per_page=100"
        events_payload = await runtime._get_json(events_url, headers=headers)
        events = events_payload.get("value", events_payload.get("events", []))
        if not isinstance(events, list):
            events = []

        last_event_per_user: dict[str, datetime] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            actor = event.get("actor")
            login = actor.get("login") if isinstance(actor, dict) else None
            created_at = event.get("created_at")
            if login and created_at:
                try:
                    ts = parse_timestamp_fn(created_at)
                except (ValueError, TypeError):
                    continue
                if login not in last_event_per_user or ts > last_event_per_user[login]:
                    last_event_per_user[login] = ts

        activity_records = []
        for member in members:
            if not isinstance(member, dict):
                continue
            login = str(member.get("login") or "").strip()
            if not login:
                continue
            activity_records.append(
                {
                    "user_id": login,
                    "email": login,
                    "full_name": member.get("name") or login,
                    "last_active_at": last_event_per_user.get(login),
                    "is_admin": member.get("site_admin", False),
                    "suspended": False,
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("github_list_members_failed", error=str(exc))
        return []
