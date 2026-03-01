from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

import app.shared.adapters.license_native_dispatch as native_dispatch
from app.shared.adapters.license_native_dispatch import (
    list_native_activity,
    resolve_native_stream_method,
    revoke_native_license,
    supported_native_vendors,
    verify_native_vendor,
)
from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError


class _Runtime:
    def __init__(self, vendor: str = "custom_vendor") -> None:
        self._vendor = vendor
        self._connector_config: dict[str, object] = {}

    def _resolve_api_key(self) -> str:
        return "token"

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        _ = url, headers, params
        return {}

    def _salesforce_instance_url(self) -> str:
        return "https://example.my.salesforce.com"


@pytest.mark.asyncio
async def test_verify_native_vendor_dispatches_and_rejects_unknown_vendor() -> None:
    runtime = _Runtime()
    verify_m365 = AsyncMock(return_value=None)
    verify_google = AsyncMock(return_value=None)
    verify_github = AsyncMock(return_value=None)

    with patch.dict(
        native_dispatch._VERIFY_FN_BY_VENDOR,
        {
            "microsoft_365": verify_m365,
            "google_workspace": verify_google,
            "github": verify_github,
        },
        clear=False,
    ):
        await verify_native_vendor(runtime, "microsoft_365")
        await verify_native_vendor(runtime, "google_workspace")
        await verify_native_vendor(runtime, "github")

    verify_m365.assert_awaited_once_with(runtime)
    verify_google.assert_awaited_once_with(runtime)
    verify_github.assert_awaited_once_with(runtime)

    with pytest.raises(ExternalAPIError, match="Unsupported native license vendor"):
        await verify_native_vendor(runtime, "unknown_vendor")


def test_resolve_native_stream_method_returns_known_handlers_only() -> None:
    m365_stream = resolve_native_stream_method("microsoft_365")
    google_stream = resolve_native_stream_method("google_workspace")

    assert m365_stream is native_dispatch.vendor_stream_microsoft_365_license_costs
    assert google_stream is native_dispatch.vendor_stream_google_workspace_license_costs
    assert resolve_native_stream_method("slack") is None
    assert resolve_native_stream_method("unknown_vendor") is None


@pytest.mark.asyncio
async def test_revoke_native_license_dispatches_sku_and_non_sku_paths() -> None:
    runtime = _Runtime()
    revoke_with_sku = AsyncMock(return_value=True)
    revoke_no_sku = AsyncMock(return_value=True)

    with (
        patch.dict(
            native_dispatch._REVOKE_WITH_SKU_FN_BY_VENDOR,
            {"google_workspace": revoke_with_sku},
            clear=False,
        ),
        patch.dict(
            native_dispatch._REVOKE_NO_SKU_FN_BY_VENDOR,
            {"github": revoke_no_sku},
            clear=False,
        ),
    ):
        result_google = await revoke_native_license(
            runtime,
            native_vendor="google_workspace",
            resource_id="user-1",
            sku_id="sku-1",
        )
        result_github = await revoke_native_license(
            runtime,
            native_vendor="github",
            resource_id="user-2",
            sku_id="ignored",
        )

    assert result_google is True
    assert result_github is True
    revoke_with_sku.assert_awaited_once_with(runtime, "user-1", "sku-1")
    revoke_no_sku.assert_awaited_once_with(runtime, "user-2")


@pytest.mark.asyncio
async def test_revoke_native_license_raises_for_unsupported_vendor() -> None:
    runtime = _Runtime()

    with pytest.raises(UnsupportedVendorError, match="not supported"):
        await revoke_native_license(
            runtime,
            native_vendor="unknown_vendor",
            resource_id="user-1",
            sku_id=None,
        )


@pytest.mark.asyncio
async def test_list_native_activity_dispatches_known_and_returns_empty_for_unknown() -> None:
    runtime = _Runtime()
    list_slack = AsyncMock(return_value=[{"vendor": "slack"}])

    with patch.dict(
        native_dispatch._ACTIVITY_FN_BY_VENDOR,
        {"slack": list_slack},
        clear=False,
    ):
        rows = await list_native_activity(runtime, "slack")
    unknown_rows = await list_native_activity(runtime, "unknown_vendor")

    assert rows == [{"vendor": "slack"}]
    assert unknown_rows == []
    list_slack.assert_awaited_once_with(runtime)


def test_supported_native_vendors_is_stable() -> None:
    assert supported_native_vendors() == (
        "microsoft_365",
        "google_workspace",
        "github",
        "slack",
        "zoom",
        "salesforce",
    )


def test_stream_method_signature_accepts_runtime_and_dates() -> None:
    stream_fn = resolve_native_stream_method("microsoft_365")
    assert stream_fn is not None
    _ = stream_fn(_Runtime(), datetime(2026, 1, 1), datetime(2026, 1, 31))
