from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_config import parse_google_workspace_license_config
from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


def _optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


async def stream_google_workspace_license_costs(
    runtime: LicenseVendorRuntime,
    start_date: datetime,
    end_date: datetime,
    *,
    as_float_fn: Callable[..., float],
) -> AsyncGenerator[dict[str, Any], None]:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}

    config = parse_google_workspace_license_config(runtime._connector_config)
    timestamp = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)

    rows_emitted = 0
    last_error: Exception | None = None

    for sku_id in config.target_skus:
        try:
            product_id = "Google-Apps"
            url = (
                "https://licensing.googleapis.com/licensing/v1/product/"
                f"{product_id}/sku/{sku_id}/usage"
            )

            payload = await runtime._get_json(url, headers=headers)
            consumed_units = as_float_fn(payload.get("totalUnits"), default=0.0)

            unit_price = config.sku_prices_usd.get(sku_id, config.default_seat_price_usd)
            total_cost = round(consumed_units * unit_price, 2)

            if timestamp < start_date or timestamp > end_date:
                continue

            rows_emitted += 1
            yield {
                "provider": "license",
                "service": sku_id,
                "region": "global",
                "usage_type": "seat_license",
                "resource_id": sku_id,
                "usage_amount": consumed_units,
                "usage_unit": "seat",
                "cost_usd": total_cost,
                "amount_raw": consumed_units,
                "currency": config.currency,
                "timestamp": timestamp,
                "source_adapter": "google_workspace_licensing",
                "tags": {
                    "vendor": "google_workspace",
                    "sku_id": sku_id,
                    "unit_price_usd": unit_price,
                },
            }
        except (ExternalAPIError, httpx.HTTPError) as exc:
            last_error = exc
            logger.warning(
                "google_workspace_sku_fetch_failed",
                sku_id=sku_id,
                error=str(exc),
            )
            continue

    if rows_emitted == 0 and last_error is not None:
        raise ExternalAPIError(
            "Google Workspace native usage fetch failed for all configured SKUs"
        ) from last_error


async def revoke_google_workspace(
    runtime: LicenseVendorRuntime, resource_id: str, sku_id: str | None = None
) -> bool:
    token = runtime._resolve_api_key()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    product_id = "Google-Apps"
    skus_to_check = (
        [sku_id]
        if sku_id
        else runtime._connector_config.get(
            "managed_skus", ["Google-Apps-For-Business", "1010020027"]
        )
    )

    success = False
    for current_sku in skus_to_check:
        try:
            url = (
                "https://licensing.googleapis.com/licensing/v1/product/"
                f"{product_id}/sku/{current_sku}/user/{resource_id}"
            )
            from app.shared.core.http import get_http_client

            client = get_http_client()
            response = await client.delete(url, headers=headers)

            if response.status_code == 204:
                logger.info(
                    "google_workspace_license_revoked",
                    user_id=resource_id,
                    sku_id=current_sku,
                )
                success = True
                break
            if response.status_code != 404:
                logger.warning(
                    "google_workspace_license_revoke_failed",
                    user_id=resource_id,
                    sku_id=current_sku,
                    status=response.status_code,
                )
        except (ExternalAPIError, httpx.HTTPError) as exc:
            logger.error(
                "google_workspace_license_revoke_error",
                user_id=resource_id,
                error=str(exc),
            )
            continue

    return success


async def list_google_workspace_activity(
    runtime: LicenseVendorRuntime,
    *,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}
    url = "https://admin.googleapis.com/admin/directory/v1/users?customer=my_customer"

    try:
        payload = await runtime._get_json(url, headers=headers)
        users_list = payload.get("users", [])

        activity_records = []
        for user in users_list:
            primary_email = user.get("primaryEmail")
            last_login_raw = user.get("lastLoginTime")
            is_super_admin = bool(user.get("isAdmin", False))
            is_delegated_admin = bool(user.get("isDelegatedAdmin", False))
            is_admin = is_super_admin or is_delegated_admin
            mfa_enabled = _optional_bool(user.get("isEnrolledIn2Sv"))
            mfa_enforced = _optional_bool(user.get("isEnforcedIn2Sv"))
            admin_role = (
                "super_admin"
                if is_super_admin
                else ("delegated_admin" if is_delegated_admin else "member")
            )

            last_active_at = None
            if last_login_raw:
                try:
                    last_active_at = parse_timestamp_fn(last_login_raw)
                except (ValueError, TypeError):
                    pass

            activity_records.append(
                {
                    "user_id": primary_email,
                    "email": primary_email,
                    "full_name": user.get("name", {}).get("fullName"),
                    "last_active_at": last_active_at,
                    "is_admin": is_admin,
                    "is_super_admin": is_super_admin,
                    "is_delegated_admin": is_delegated_admin,
                    "admin_role": admin_role,
                    "mfa_enabled": mfa_enabled,
                    "two_factor_authentication": mfa_enabled,
                    "mfa_enforced": mfa_enforced,
                    "suspended": user.get("suspended", False),
                    "creation_time": user.get("creationTime"),
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("google_workspace_list_users_failed", error=str(exc))
        return []
