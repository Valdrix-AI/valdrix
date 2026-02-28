from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


async def revoke_slack(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    token = runtime._resolve_api_key()
    url = "https://slack.com/api/admin.users.remove"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    team_id = runtime._connector_config.get("slack_team_id")
    if not team_id:
        logger.warning("slack_revoke_failed_no_team_id", user_id=resource_id)
        return False

    payload = {"team_id": team_id, "user_id": resource_id}

    try:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.post(url, headers=headers, json=payload)
        data = response.json()

        if data.get("ok"):
            logger.info("slack_user_deactivated", user_id=resource_id)
            return True

        logger.warning(
            "slack_user_deactivation_failed",
            user_id=resource_id,
            error=data.get("error"),
        )
        return False
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("slack_user_deactivation_error", user_id=resource_id, error=str(exc))
        return False


async def list_slack_activity(runtime: LicenseVendorRuntime) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://slack.com/api/team.accessLogs"

    try:
        payload = await runtime._get_json(url, headers=headers)
        if not payload.get("ok"):
            logger.warning("slack_activity_fetch_failed", error=payload.get("error"))
            return []

        logs = payload.get("logins", [])
        user_activity: dict[str, int] = {}

        for log in logs:
            uid = log.get("user_id")
            ts = log.get("date_last")
            if uid and ts:
                user_activity[uid] = max(user_activity.get(uid, 0), ts)

        activity_records = []
        users_url = "https://slack.com/api/users.list"
        users_payload = await runtime._get_json(users_url, headers=headers)
        for user in users_payload.get("members", []):
            uid = user.get("id")
            last_ts = user_activity.get(uid)
            last_active_at = (
                datetime.fromtimestamp(last_ts, tz=timezone.utc) if last_ts else None
            )

            activity_records.append(
                {
                    "user_id": uid,
                    "email": user.get("profile", {}).get("email"),
                    "full_name": user.get("real_name") or user.get("name"),
                    "last_active_at": last_active_at,
                    "is_admin": user.get("is_admin", False),
                    "suspended": user.get("deleted", False),
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("slack_list_activity_failed", error=str(exc))
        return []
