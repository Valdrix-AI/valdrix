from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


async def revoke_zoom(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.zoom.us/v2/users/{resource_id}?action=disassociate"

    try:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.delete(url, headers=headers)

        if response.status_code == 204:
            logger.info("zoom_user_disassociated", user_id=resource_id)
            return True

        logger.warning(
            "zoom_user_disassociate_failed",
            user_id=resource_id,
            status=response.status_code,
        )
        return False
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("zoom_user_disassociate_error", user_id=resource_id, error=str(exc))
        return False


async def list_zoom_activity(
    runtime: LicenseVendorRuntime,
    *,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://api.zoom.us/v2/users"

    try:
        payload = await runtime._get_json(url, headers=headers)
        users_list = payload.get("users", [])

        activity_records = []
        for user in users_list:
            last_login_raw = user.get("last_login_time")
            last_active_at = None
            if last_login_raw:
                try:
                    last_active_at = parse_timestamp_fn(last_login_raw)
                except (ValueError, TypeError):
                    pass

            activity_records.append(
                {
                    "user_id": user.get("id"),
                    "email": user.get("email"),
                    "full_name": (
                        f"{user.get('first_name', '')} {user.get('last_name', '')}"
                    ).strip(),
                    "last_active_at": last_active_at,
                    "is_admin": user.get("role_name") == "Owner",
                    "suspended": user.get("status") == "inactive",
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("zoom_list_users_failed", error=str(exc))
        return []
