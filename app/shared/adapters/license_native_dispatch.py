from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Awaitable, Callable, TypeAlias

from app.shared.adapters.feed_utils import as_float, parse_timestamp
from app.shared.adapters.license_vendor_github import (
    list_github_activity as _list_github_activity_impl,
    revoke_github as vendor_revoke_github,
)
from app.shared.adapters.license_vendor_google import (
    list_google_workspace_activity as _list_google_workspace_activity_impl,
    revoke_google_workspace as vendor_revoke_google_workspace,
    stream_google_workspace_license_costs as _stream_google_workspace_license_costs_impl,
)
from app.shared.adapters.license_vendor_microsoft import (
    list_microsoft_365_activity as _list_microsoft_365_activity_impl,
    revoke_microsoft_365 as vendor_revoke_microsoft_365,
    stream_microsoft_365_license_costs as _stream_microsoft_365_license_costs_impl,
)
from app.shared.adapters.license_vendor_salesforce import (
    list_salesforce_activity as _list_salesforce_activity_impl,
    revoke_salesforce as vendor_revoke_salesforce,
)
from app.shared.adapters.license_vendor_slack import (
    list_slack_activity as vendor_list_slack_activity,
    revoke_slack as vendor_revoke_slack,
)
from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.adapters.license_vendor_verify import (
    verify_github as vendor_verify_github,
    verify_google_workspace as vendor_verify_google_workspace,
    verify_microsoft_365 as vendor_verify_microsoft_365,
    verify_salesforce as vendor_verify_salesforce,
    verify_slack as vendor_verify_slack,
    verify_zoom as vendor_verify_zoom,
)
from app.shared.adapters.license_vendor_zoom import (
    list_zoom_activity as _list_zoom_activity_impl,
    revoke_zoom as vendor_revoke_zoom,
)
from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError

VerifyFn: TypeAlias = Callable[[LicenseVendorRuntime], Awaitable[None]]
StreamFn: TypeAlias = Callable[
    [LicenseVendorRuntime, datetime, datetime],
    AsyncGenerator[dict[str, Any], None],
]
RevokeWithSkuFn: TypeAlias = Callable[
    [LicenseVendorRuntime, str, str | None], Awaitable[bool]
]
RevokeNoSkuFn: TypeAlias = Callable[[LicenseVendorRuntime, str], Awaitable[bool]]
ActivityFn: TypeAlias = Callable[
    [LicenseVendorRuntime], Awaitable[list[dict[str, Any]]]
]


async def vendor_stream_google_workspace_license_costs(
    runtime: LicenseVendorRuntime, start_date: datetime, end_date: datetime
) -> AsyncGenerator[dict[str, Any], None]:
    async for row in _stream_google_workspace_license_costs_impl(
        runtime,
        start_date,
        end_date,
        as_float_fn=as_float,
    ):
        yield row


async def vendor_stream_microsoft_365_license_costs(
    runtime: LicenseVendorRuntime, start_date: datetime, end_date: datetime
) -> AsyncGenerator[dict[str, Any], None]:
    async for row in _stream_microsoft_365_license_costs_impl(
        runtime,
        start_date,
        end_date,
        as_float_fn=as_float,
    ):
        yield row


async def vendor_list_google_workspace_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await _list_google_workspace_activity_impl(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def vendor_list_microsoft_365_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await _list_microsoft_365_activity_impl(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def vendor_list_github_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await _list_github_activity_impl(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def vendor_list_zoom_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await _list_zoom_activity_impl(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def vendor_list_salesforce_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await _list_salesforce_activity_impl(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )

_SUPPORTED_NATIVE_VENDORS: tuple[str, ...] = (
    "microsoft_365",
    "google_workspace",
    "github",
    "slack",
    "zoom",
    "salesforce",
)

_VERIFY_FN_BY_VENDOR: dict[str, VerifyFn] = {
    "microsoft_365": vendor_verify_microsoft_365,
    "google_workspace": vendor_verify_google_workspace,
    "github": vendor_verify_github,
    "slack": vendor_verify_slack,
    "zoom": vendor_verify_zoom,
    "salesforce": vendor_verify_salesforce,
}

_STREAM_FN_BY_VENDOR: dict[str, StreamFn] = {
    "microsoft_365": vendor_stream_microsoft_365_license_costs,
    "google_workspace": vendor_stream_google_workspace_license_costs,
}

_REVOKE_WITH_SKU_FN_BY_VENDOR: dict[str, RevokeWithSkuFn] = {
    "google_workspace": vendor_revoke_google_workspace,
    "microsoft_365": vendor_revoke_microsoft_365,
}

_REVOKE_NO_SKU_FN_BY_VENDOR: dict[str, RevokeNoSkuFn] = {
    "github": vendor_revoke_github,
    "slack": vendor_revoke_slack,
    "zoom": vendor_revoke_zoom,
    "salesforce": vendor_revoke_salesforce,
}

_ACTIVITY_FN_BY_VENDOR: dict[str, ActivityFn] = {
    "google_workspace": vendor_list_google_workspace_activity,
    "microsoft_365": vendor_list_microsoft_365_activity,
    "github": vendor_list_github_activity,
    "slack": vendor_list_slack_activity,
    "zoom": vendor_list_zoom_activity,
    "salesforce": vendor_list_salesforce_activity,
}


def supported_native_vendors() -> tuple[str, ...]:
    return _SUPPORTED_NATIVE_VENDORS


async def verify_native_vendor(
    runtime: LicenseVendorRuntime, native_vendor: str
) -> None:
    verify_fn = _VERIFY_FN_BY_VENDOR.get(native_vendor)
    if verify_fn is None:
        raise ExternalAPIError(f"Unsupported native license vendor '{native_vendor}'")
    await verify_fn(runtime)


def resolve_native_stream_method(native_vendor: str) -> StreamFn | None:
    return _STREAM_FN_BY_VENDOR.get(native_vendor)


async def revoke_native_license(
    runtime: LicenseVendorRuntime,
    *,
    native_vendor: str | None,
    resource_id: str,
    sku_id: str | None,
) -> bool:
    if native_vendor is not None:
        revoke_with_sku = _REVOKE_WITH_SKU_FN_BY_VENDOR.get(native_vendor)
        if revoke_with_sku is not None:
            return await revoke_with_sku(runtime, resource_id, sku_id)

        revoke_no_sku = _REVOKE_NO_SKU_FN_BY_VENDOR.get(native_vendor)
        if revoke_no_sku is not None:
            return await revoke_no_sku(runtime, resource_id)

    raise UnsupportedVendorError(
        (
            f"License revocation is not supported for vendor '{runtime._vendor}'. "
            "Use a supported native vendor or manual follow-up workflow."
        ),
        details={"vendor": runtime._vendor, "operation": "revoke_license"},
    )


async def list_native_activity(
    runtime: LicenseVendorRuntime, native_vendor: str
) -> list[dict[str, Any]]:
    activity_fn = _ACTIVITY_FN_BY_VENDOR.get(native_vendor)
    if activity_fn is None:
        return []
    return await activity_fn(runtime)
