from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


async def revoke_salesforce(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    token = runtime._resolve_api_key()
    try:
        instance_url = runtime._salesforce_instance_url()
    except ExternalAPIError:
        logger.warning("salesforce_revoke_failed_no_url", user_id=resource_id)
        return False
    api_version = runtime._connector_config.get("salesforce_api_version", "v60.0")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url = f"{instance_url}/services/data/{api_version}/sobjects/User/{resource_id}"

    try:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.patch(url, headers=headers, json={"IsActive": False})

        if response.status_code == 204:
            logger.info("salesforce_user_deactivated", user_id=resource_id)
            return True

        logger.warning(
            "salesforce_user_deactivation_failed",
            user_id=resource_id,
            status=response.status_code,
        )
        return False
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("salesforce_user_deactivation_error", user_id=resource_id, error=str(exc))
        return False


async def list_salesforce_activity(
    runtime: LicenseVendorRuntime,
    *,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    try:
        instance_url = runtime._salesforce_instance_url()
    except ExternalAPIError:
        return []
    api_version = runtime._connector_config.get("salesforce_api_version", "v60.0")

    headers = {"Authorization": f"Bearer {token}"}
    query = "SELECT+Id,Email,Name,LastLoginDate,IsActive,Profile.Name+FROM+User"
    url = f"{instance_url}/services/data/{api_version}/query?q={query}"

    try:
        payload = await runtime._get_json(url, headers=headers)
        records = payload.get("records", [])

        activity_records = []
        for user in records:
            last_login_raw = user.get("LastLoginDate")
            last_active_at = None
            if last_login_raw:
                try:
                    last_active_at = parse_timestamp_fn(last_login_raw)
                except (ValueError, TypeError):
                    pass

            activity_records.append(
                {
                    "user_id": user.get("Id"),
                    "email": user.get("Email"),
                    "full_name": user.get("Name"),
                    "last_active_at": last_active_at,
                    "is_admin": (user.get("Profile", {}) or {}).get("Name")
                    == "System Administrator",
                    "suspended": not user.get("IsActive", True),
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("salesforce_list_users_failed", error=str(exc))
        return []
