from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.core.exceptions import ExternalAPIError

logger = structlog.get_logger()


async def stream_microsoft_365_license_costs(
    runtime: LicenseVendorRuntime,
    start_date: datetime,
    end_date: datetime,
    *,
    as_float_fn: Callable[..., float],
) -> AsyncGenerator[dict[str, Any], None]:
    token = runtime._resolve_api_key()
    payload = await runtime._get_json(
        "https://graph.microsoft.com/v1.0/subscribedSkus",
        headers={"Authorization": f"Bearer {token}"},
    )
    entries = payload.get("value")
    if not isinstance(entries, list):
        raise ExternalAPIError("Invalid Microsoft Graph subscribedSkus payload")

    sku_prices_raw = runtime._connector_config.get("sku_prices")
    sku_prices: dict[str, float] = {}
    if isinstance(sku_prices_raw, dict):
        for key, value in sku_prices_raw.items():
            if isinstance(key, str):
                sku_prices[key.strip().upper()] = as_float_fn(value)
    default_price = as_float_fn(
        runtime._connector_config.get("default_seat_price_usd"), default=0.0
    )
    default_currency = str(runtime._connector_config.get("currency") or "USD").upper()
    timestamp = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)

    for sku in entries:
        if not isinstance(sku, dict):
            continue
        sku_code = str(sku.get("skuPartNumber") or sku.get("skuId") or "M365_SKU").upper()
        consumed_units = as_float_fn(sku.get("consumedUnits"), default=0.0)
        prepaid = sku.get("prepaidUnits")
        if consumed_units <= 0 and isinstance(prepaid, dict):
            consumed_units = as_float_fn(prepaid.get("enabled"), default=0.0)

        unit_price = sku_prices.get(sku_code, default_price)
        total_cost = round(consumed_units * unit_price, 2)

        if timestamp < start_date or timestamp > end_date:
            continue

        yield {
            "provider": "license",
            "service": sku_code,
            "region": "global",
            "usage_type": "seat_license",
            "resource_id": str(sku.get("skuId") or sku_code).strip() or None,
            "usage_amount": consumed_units,
            "usage_unit": "seat",
            "cost_usd": total_cost,
            "amount_raw": consumed_units,
            "currency": default_currency,
            "timestamp": timestamp,
            "source_adapter": "license_microsoft_graph",
            "tags": {
                "vendor": "microsoft_365",
                "sku_id": str(sku.get("skuId") or ""),
                "unit_price_usd": unit_price,
                "consumed_units": consumed_units,
            },
        }


async def revoke_microsoft_365(
    runtime: LicenseVendorRuntime, resource_id: str, sku_id: str | None = None
) -> bool:
    token = runtime._resolve_api_key()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    if not sku_id:
        logger.warning("m365_revoke_failed_no_sku", user_id=resource_id)
        return False

    url = f"https://graph.microsoft.com/v1.0/users/{resource_id}/assignLicense"
    payload = {"addLicenses": [], "removeLicenses": [sku_id]}

    try:
        from app.shared.core.http import get_http_client

        client = get_http_client()
        response = await client.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            logger.info("m365_license_revoked", user_id=resource_id, sku_id=sku_id)
            return True

        logger.warning(
            "m365_license_revoke_failed",
            user_id=resource_id,
            status=response.status_code,
        )
        return False
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("m365_license_revoke_error", user_id=resource_id, error=str(exc))
        return False


async def list_microsoft_365_activity(
    runtime: LicenseVendorRuntime,
    *,
    parse_timestamp_fn: Callable[[Any], datetime],
) -> list[dict[str, Any]]:
    token = runtime._resolve_api_key()
    headers = {"Authorization": f"Bearer {token}"}

    admin_upns_raw = runtime._connector_config.get("admin_upns", [])
    admin_upns = {
        item.strip().lower()
        for item in admin_upns_raw
        if isinstance(item, str) and item.strip()
    }

    url = (
        "https://graph.microsoft.com/v1.0/users?"
        "$select=displayName,userPrincipalName,id,signInActivity,accountEnabled"
    )

    try:
        payload = await runtime._get_json(url, headers=headers)
        users_list = payload.get("value", [])

        activity_records = []
        for user in users_list:
            email = user.get("userPrincipalName")
            display_name = user.get("displayName")
            sign_in = user.get("signInActivity", {})

            last_login_raw = sign_in.get(
                "lastSuccessfulSignInDateTime"
            ) or sign_in.get("lastSignInDateTime")

            last_active_at = None
            if last_login_raw:
                try:
                    last_active_at = parse_timestamp_fn(last_login_raw)
                except (ValueError, TypeError):
                    pass

            activity_records.append(
                {
                    "user_id": user.get("id"),
                    "email": email,
                    "full_name": display_name,
                    "last_active_at": last_active_at,
                    "is_admin": bool(email and email.lower() in admin_upns),
                    "suspended": not user.get("accountEnabled", True),
                }
            )
        return activity_records
    except (ExternalAPIError, httpx.HTTPError) as exc:
        logger.error("m365_list_users_failed", error=str(exc))
        return []
