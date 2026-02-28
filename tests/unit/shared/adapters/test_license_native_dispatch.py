from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.shared.adapters.license_native_dispatch import (
    list_native_activity,
    resolve_native_stream_method,
    revoke_native_license,
    supported_native_vendors,
    verify_native_vendor,
)
from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError


class _Runtime:
    def __init__(self) -> None:
        self._vendor = "custom_vendor"

        self._verify_microsoft_365 = AsyncMock()
        self._verify_google_workspace = AsyncMock()
        self._verify_github = AsyncMock()
        self._verify_slack = AsyncMock()
        self._verify_zoom = AsyncMock()
        self._verify_salesforce = AsyncMock()

        self._revoke_google_workspace = AsyncMock(return_value=True)
        self._revoke_microsoft_365 = AsyncMock(return_value=True)
        self._revoke_github = AsyncMock(return_value=True)
        self._revoke_slack = AsyncMock(return_value=True)
        self._revoke_zoom = AsyncMock(return_value=True)
        self._revoke_salesforce = AsyncMock(return_value=True)

        self._list_google_workspace_activity = AsyncMock(return_value=[{"vendor": "google_workspace"}])
        self._list_microsoft_365_activity = AsyncMock(return_value=[{"vendor": "microsoft_365"}])
        self._list_github_activity = AsyncMock(return_value=[{"vendor": "github"}])
        self._list_slack_activity = AsyncMock(return_value=[{"vendor": "slack"}])
        self._list_zoom_activity = AsyncMock(return_value=[{"vendor": "zoom"}])
        self._list_salesforce_activity = AsyncMock(return_value=[{"vendor": "salesforce"}])

    async def _stream_google_workspace_license_costs(
        self, start_date: datetime, end_date: datetime
    ) -> AsyncGenerator[dict[str, Any], None]:
        _ = (start_date, end_date)
        yield {"vendor": "google_workspace"}

    async def _stream_microsoft_365_license_costs(
        self, start_date: datetime, end_date: datetime
    ) -> AsyncGenerator[dict[str, Any], None]:
        _ = (start_date, end_date)
        yield {"vendor": "microsoft_365"}


@pytest.mark.asyncio
async def test_verify_native_vendor_dispatches_and_rejects_unknown_vendor() -> None:
    runtime = _Runtime()

    await verify_native_vendor(runtime, "microsoft_365")
    await verify_native_vendor(runtime, "google_workspace")
    await verify_native_vendor(runtime, "github")

    runtime._verify_microsoft_365.assert_awaited_once()
    runtime._verify_google_workspace.assert_awaited_once()
    runtime._verify_github.assert_awaited_once()

    with pytest.raises(ExternalAPIError, match="Unsupported native license vendor"):
        await verify_native_vendor(runtime, "unknown_vendor")


@pytest.mark.asyncio
async def test_resolve_native_stream_method_returns_known_handlers_only() -> None:
    runtime = _Runtime()

    m365_stream = resolve_native_stream_method(runtime, "microsoft_365")
    google_stream = resolve_native_stream_method(runtime, "google_workspace")

    assert m365_stream is not None
    assert google_stream is not None
    m365_rows = [
        row
        async for row in m365_stream(datetime(2026, 1, 1), datetime(2026, 1, 31))
    ]
    google_rows = [
        row
        async for row in google_stream(datetime(2026, 1, 1), datetime(2026, 1, 31))
    ]
    assert m365_rows == [{"vendor": "microsoft_365"}]
    assert google_rows == [{"vendor": "google_workspace"}]
    assert resolve_native_stream_method(runtime, "slack") is None
    assert resolve_native_stream_method(runtime, "unknown_vendor") is None


@pytest.mark.asyncio
async def test_revoke_native_license_dispatches_sku_and_non_sku_paths() -> None:
    runtime = _Runtime()

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
    runtime._revoke_google_workspace.assert_awaited_once_with("user-1", "sku-1")
    runtime._revoke_github.assert_awaited_once_with("user-2")


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

    rows = await list_native_activity(runtime, "slack")
    unknown_rows = await list_native_activity(runtime, "unknown_vendor")

    assert rows == [{"vendor": "slack"}]
    assert unknown_rows == []
    runtime._list_slack_activity.assert_awaited_once()


def test_supported_native_vendors_is_stable() -> None:
    assert supported_native_vendors() == (
        "microsoft_365",
        "google_workspace",
        "github",
        "slack",
        "zoom",
        "salesforce",
    )
