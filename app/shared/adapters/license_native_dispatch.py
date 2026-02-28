from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Awaitable, Callable, Protocol, cast

from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError

_SUPPORTED_NATIVE_VENDORS: tuple[str, ...] = (
    "microsoft_365",
    "google_workspace",
    "github",
    "slack",
    "zoom",
    "salesforce",
)

_VERIFY_METHOD_BY_VENDOR: dict[str, str] = {
    "microsoft_365": "_verify_microsoft_365",
    "google_workspace": "_verify_google_workspace",
    "github": "_verify_github",
    "slack": "_verify_slack",
    "zoom": "_verify_zoom",
    "salesforce": "_verify_salesforce",
}

_REVOKE_METHOD_BY_VENDOR: dict[str, tuple[str, bool]] = {
    "google_workspace": ("_revoke_google_workspace", True),
    "microsoft_365": ("_revoke_microsoft_365", True),
    "github": ("_revoke_github", False),
    "slack": ("_revoke_slack", False),
    "zoom": ("_revoke_zoom", False),
    "salesforce": ("_revoke_salesforce", False),
}

_ACTIVITY_METHOD_BY_VENDOR: dict[str, str] = {
    "google_workspace": "_list_google_workspace_activity",
    "microsoft_365": "_list_microsoft_365_activity",
    "github": "_list_github_activity",
    "slack": "_list_slack_activity",
    "zoom": "_list_zoom_activity",
    "salesforce": "_list_salesforce_activity",
}

_STREAM_METHOD_BY_VENDOR: dict[str, str] = {
    "microsoft_365": "_stream_microsoft_365_license_costs",
    "google_workspace": "_stream_google_workspace_license_costs",
}


class LicenseNativeDispatchRuntime(Protocol):
    @property
    def _vendor(self) -> str: ...

    async def _verify_microsoft_365(self) -> None: ...

    async def _verify_google_workspace(self) -> None: ...

    async def _verify_github(self) -> None: ...

    async def _verify_slack(self) -> None: ...

    async def _verify_zoom(self) -> None: ...

    async def _verify_salesforce(self) -> None: ...

    def _stream_microsoft_365_license_costs(
        self, start_date: datetime, end_date: datetime
    ) -> AsyncGenerator[dict[str, Any], None]: ...

    def _stream_google_workspace_license_costs(
        self, start_date: datetime, end_date: datetime
    ) -> AsyncGenerator[dict[str, Any], None]: ...

    async def _revoke_google_workspace(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool: ...

    async def _revoke_microsoft_365(
        self, resource_id: str, sku_id: str | None = None
    ) -> bool: ...

    async def _revoke_github(self, resource_id: str) -> bool: ...

    async def _revoke_slack(self, resource_id: str) -> bool: ...

    async def _revoke_zoom(self, resource_id: str) -> bool: ...

    async def _revoke_salesforce(self, resource_id: str) -> bool: ...

    async def _list_google_workspace_activity(self) -> list[dict[str, Any]]: ...

    async def _list_microsoft_365_activity(self) -> list[dict[str, Any]]: ...

    async def _list_github_activity(self) -> list[dict[str, Any]]: ...

    async def _list_slack_activity(self) -> list[dict[str, Any]]: ...

    async def _list_zoom_activity(self) -> list[dict[str, Any]]: ...

    async def _list_salesforce_activity(self) -> list[dict[str, Any]]: ...


def supported_native_vendors() -> tuple[str, ...]:
    return _SUPPORTED_NATIVE_VENDORS


async def verify_native_vendor(
    runtime: LicenseNativeDispatchRuntime, native_vendor: str
) -> None:
    method_name = _VERIFY_METHOD_BY_VENDOR.get(native_vendor)
    if method_name is None:
        raise ExternalAPIError(f"Unsupported native license vendor '{native_vendor}'")
    verify_method = cast(Callable[[], Awaitable[None]], getattr(runtime, method_name))
    await verify_method()


def resolve_native_stream_method(
    runtime: LicenseNativeDispatchRuntime, native_vendor: str
) -> Callable[[datetime, datetime], AsyncGenerator[dict[str, Any], None]] | None:
    method_name = _STREAM_METHOD_BY_VENDOR.get(native_vendor)
    if method_name is None:
        return None
    return cast(
        Callable[[datetime, datetime], AsyncGenerator[dict[str, Any], None]],
        getattr(runtime, method_name),
    )


async def revoke_native_license(
    runtime: LicenseNativeDispatchRuntime,
    *,
    native_vendor: str | None,
    resource_id: str,
    sku_id: str | None,
) -> bool:
    revoke_method = (
        _REVOKE_METHOD_BY_VENDOR.get(native_vendor) if native_vendor is not None else None
    )
    if revoke_method is not None:
        method_name, supports_sku = revoke_method
        if supports_sku:
            revoke_with_sku = cast(
                Callable[[str, str | None], Awaitable[bool]],
                getattr(runtime, method_name),
            )
            return await revoke_with_sku(resource_id, sku_id)
        revoke_without_sku = cast(
            Callable[[str], Awaitable[bool]],
            getattr(runtime, method_name),
        )
        return await revoke_without_sku(resource_id)

    raise UnsupportedVendorError(
        (
            f"License revocation is not supported for vendor '{runtime._vendor}'. "
            "Use a supported native vendor or manual follow-up workflow."
        ),
        details={"vendor": runtime._vendor, "operation": "revoke_license"},
    )


async def list_native_activity(
    runtime: LicenseNativeDispatchRuntime, native_vendor: str
) -> list[dict[str, Any]]:
    method_name = _ACTIVITY_METHOD_BY_VENDOR.get(native_vendor)
    if method_name is None:
        return []
    activity_method = cast(
        Callable[[], Awaitable[list[dict[str, Any]]]],
        getattr(runtime, method_name),
    )
    return await activity_method()
