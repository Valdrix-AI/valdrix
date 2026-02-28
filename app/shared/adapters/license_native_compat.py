from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, cast

from app.shared.adapters.license_native_dispatch import (
    LicenseNativeDispatchRuntime,
    verify_native_vendor as dispatch_verify_native_vendor,
)
from app.shared.adapters.license_vendor_ops import (
    list_github_activity as vendor_list_github_activity,
    list_google_workspace_activity as vendor_list_google_workspace_activity,
    list_microsoft_365_activity as vendor_list_microsoft_365_activity,
    list_salesforce_activity as vendor_list_salesforce_activity,
    list_slack_activity as vendor_list_slack_activity,
    list_zoom_activity as vendor_list_zoom_activity,
    revoke_github as vendor_revoke_github,
    revoke_google_workspace as vendor_revoke_google_workspace,
    revoke_microsoft_365 as vendor_revoke_microsoft_365,
    revoke_salesforce as vendor_revoke_salesforce,
    revoke_slack as vendor_revoke_slack,
    revoke_zoom as vendor_revoke_zoom,
    stream_google_workspace_license_costs as vendor_stream_google_workspace_license_costs,
    stream_microsoft_365_license_costs as vendor_stream_microsoft_365_license_costs,
    verify_github as vendor_verify_github,
    verify_google_workspace as vendor_verify_google_workspace,
    verify_microsoft_365 as vendor_verify_microsoft_365,
    verify_salesforce as vendor_verify_salesforce,
    verify_slack as vendor_verify_slack,
    verify_zoom as vendor_verify_zoom,
)
from app.shared.adapters.license_vendor_types import LicenseVendorRuntime


class LicenseNativeCompatMixin:
    """
    Compatibility facade for native vendor operations.

    This keeps existing private method seams stable while vendor logic remains
    implemented in dedicated dispatch/vendor modules.
    """

    async def _verify_native_vendor(self, native_vendor: str) -> None:
        runtime = cast(LicenseNativeDispatchRuntime, self)
        await dispatch_verify_native_vendor(runtime, native_vendor)

    async def _verify_microsoft_365(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_microsoft_365(runtime)

    async def _verify_google_workspace(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_google_workspace(runtime)

    async def _verify_github(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_github(runtime)

    async def _verify_slack(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_slack(runtime)

    async def _verify_zoom(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_zoom(runtime)

    async def _verify_salesforce(self) -> None:
        runtime = cast(LicenseVendorRuntime, self)
        await vendor_verify_salesforce(runtime)

    async def _stream_google_workspace_license_costs(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        runtime = cast(LicenseVendorRuntime, self)
        async for row in vendor_stream_google_workspace_license_costs(
            runtime, start_date, end_date
        ):
            yield row

    async def _stream_microsoft_365_license_costs(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> AsyncGenerator[dict[str, Any], None]:
        runtime = cast(LicenseVendorRuntime, self)
        async for row in vendor_stream_microsoft_365_license_costs(
            runtime, start_date, end_date
        ):
            yield row

    async def _revoke_google_workspace(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_google_workspace(runtime, resource_id, sku_id)

    async def _revoke_microsoft_365(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_microsoft_365(runtime, resource_id, sku_id)

    async def _revoke_github(self, resource_id: str) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_github(runtime, resource_id)

    async def _revoke_zoom(self, resource_id: str) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_zoom(runtime, resource_id)

    async def _revoke_slack(self, resource_id: str) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_slack(runtime, resource_id)

    async def _revoke_salesforce(self, resource_id: str) -> bool:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_revoke_salesforce(runtime, resource_id)

    async def _list_google_workspace_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_google_workspace_activity(runtime)

    async def _list_microsoft_365_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_microsoft_365_activity(runtime)

    async def _list_github_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_github_activity(runtime)

    async def _list_zoom_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_zoom_activity(runtime)

    async def _list_slack_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_slack_activity(runtime)

    async def _list_salesforce_activity(self) -> list[dict[str, Any]]:
        runtime = cast(LicenseVendorRuntime, self)
        return await vendor_list_salesforce_activity(runtime)
