from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from app.shared.adapters.feed_utils import as_float, parse_timestamp
from app.shared.adapters.license_vendor_github import (
    list_github_activity as github_list_github_activity,
    revoke_github as github_revoke_github,
)
from app.shared.adapters.license_vendor_google import (
    list_google_workspace_activity as google_list_google_workspace_activity,
    revoke_google_workspace as google_revoke_google_workspace,
    stream_google_workspace_license_costs as google_stream_google_workspace_license_costs,
)
from app.shared.adapters.license_vendor_microsoft import (
    list_microsoft_365_activity as microsoft_list_microsoft_365_activity,
    revoke_microsoft_365 as microsoft_revoke_microsoft_365,
    stream_microsoft_365_license_costs as microsoft_stream_microsoft_365_license_costs,
)
from app.shared.adapters.license_vendor_salesforce import (
    list_salesforce_activity as salesforce_list_salesforce_activity,
    revoke_salesforce as salesforce_revoke_salesforce,
)
from app.shared.adapters.license_vendor_slack import (
    list_slack_activity as slack_list_slack_activity,
    revoke_slack as slack_revoke_slack,
)
from app.shared.adapters.license_vendor_types import LicenseVendorRuntime
from app.shared.adapters.license_vendor_verify import (
    verify_github,
    verify_google_workspace,
    verify_microsoft_365,
    verify_salesforce,
    verify_slack,
    verify_zoom,
)
from app.shared.adapters.license_vendor_zoom import (
    list_zoom_activity as zoom_list_zoom_activity,
    revoke_zoom as zoom_revoke_zoom,
)
from app.shared.core.exceptions import ExternalAPIError

__all__ = [
    "list_github_activity",
    "list_google_workspace_activity",
    "list_microsoft_365_activity",
    "list_salesforce_activity",
    "list_slack_activity",
    "list_zoom_activity",
    "revoke_github",
    "revoke_google_workspace",
    "revoke_microsoft_365",
    "revoke_salesforce",
    "revoke_slack",
    "revoke_zoom",
    "stream_google_workspace_license_costs",
    "stream_microsoft_365_license_costs",
    "verify_github",
    "verify_google_workspace",
    "verify_microsoft_365",
    "verify_native_vendor",
    "verify_salesforce",
    "verify_slack",
    "verify_zoom",
]


async def verify_native_vendor(
    runtime: LicenseVendorRuntime, native_vendor: str
) -> None:
    if native_vendor == "microsoft_365":
        await verify_microsoft_365(runtime)
        return
    if native_vendor == "google_workspace":
        await verify_google_workspace(runtime)
        return
    if native_vendor == "github":
        await verify_github(runtime)
        return
    if native_vendor == "slack":
        await verify_slack(runtime)
        return
    if native_vendor == "zoom":
        await verify_zoom(runtime)
        return
    if native_vendor == "salesforce":
        await verify_salesforce(runtime)
        return
    raise ExternalAPIError(f"Unsupported native license vendor '{native_vendor}'")


async def stream_google_workspace_license_costs(
    runtime: LicenseVendorRuntime,
    start_date: datetime,
    end_date: datetime,
) -> AsyncGenerator[dict[str, Any], None]:
    async for row in google_stream_google_workspace_license_costs(
        runtime,
        start_date,
        end_date,
        as_float_fn=as_float,
    ):
        yield row


async def stream_microsoft_365_license_costs(
    runtime: LicenseVendorRuntime,
    start_date: datetime,
    end_date: datetime,
) -> AsyncGenerator[dict[str, Any], None]:
    async for row in microsoft_stream_microsoft_365_license_costs(
        runtime,
        start_date,
        end_date,
        as_float_fn=as_float,
    ):
        yield row


async def revoke_google_workspace(
    runtime: LicenseVendorRuntime, resource_id: str, sku_id: str | None = None
) -> bool:
    return await google_revoke_google_workspace(runtime, resource_id, sku_id)


async def revoke_microsoft_365(
    runtime: LicenseVendorRuntime, resource_id: str, sku_id: str | None = None
) -> bool:
    return await microsoft_revoke_microsoft_365(runtime, resource_id, sku_id)


async def revoke_github(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    return await github_revoke_github(runtime, resource_id)


async def revoke_zoom(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    return await zoom_revoke_zoom(runtime, resource_id)


async def revoke_slack(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    return await slack_revoke_slack(runtime, resource_id)


async def revoke_salesforce(runtime: LicenseVendorRuntime, resource_id: str) -> bool:
    return await salesforce_revoke_salesforce(runtime, resource_id)


async def list_microsoft_365_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await microsoft_list_microsoft_365_activity(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def list_github_activity(runtime: LicenseVendorRuntime) -> list[dict[str, Any]]:
    return await github_list_github_activity(runtime, parse_timestamp_fn=parse_timestamp)


async def list_zoom_activity(runtime: LicenseVendorRuntime) -> list[dict[str, Any]]:
    return await zoom_list_zoom_activity(runtime, parse_timestamp_fn=parse_timestamp)


async def list_slack_activity(runtime: LicenseVendorRuntime) -> list[dict[str, Any]]:
    return await slack_list_slack_activity(runtime)


async def list_salesforce_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await salesforce_list_salesforce_activity(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )


async def list_google_workspace_activity(
    runtime: LicenseVendorRuntime,
) -> list[dict[str, Any]]:
    return await google_list_google_workspace_activity(
        runtime,
        parse_timestamp_fn=parse_timestamp,
    )
