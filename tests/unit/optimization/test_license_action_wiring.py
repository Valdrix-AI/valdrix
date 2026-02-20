from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.domain.actions.base import (
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions.license.base import LicenseReclaimSeatAction
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.core.credentials import LicenseCredentials


@pytest.mark.asyncio
async def test_license_action_builds_typed_credentials_from_dict() -> None:
    action = LicenseReclaimSeatAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "google_workspace",
            "auth_method": "oauth",
            "api_key": "test-token",
            "connector_config": {"k": "v"},
            "license_feed": [{"user_id": "u1"}],
        },
        parameters={"sku_id": "sku-123"},
    )

    with patch(
        "app.modules.optimization.domain.actions.license.base.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.revoke_license = AsyncMock(return_value=True)
        result = await action._perform_action("user-1", context)

    adapter_cls.return_value.revoke_license.assert_awaited_once_with(
        "user-1", sku_id="sku-123"
    )
    assert result.status == ExecutionStatus.SUCCESS
    created_credentials = adapter_cls.call_args.args[0]
    assert isinstance(created_credentials, LicenseCredentials)
    assert created_credentials.vendor == "google_workspace"
    assert created_credentials.auth_method == "oauth"
    assert created_credentials.license_feed == [{"user_id": "u1"}]


@pytest.mark.asyncio
async def test_remediation_resolve_credentials_includes_license_wiring() -> None:
    connection_id = uuid4()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        vendor="custom_vendor",
        auth_method="manual",
        api_key=None,
        connector_config={"default_seat_price_usd": 9.5},
        license_feed=[{"user_id": "feed-user-1"}],
    )
    db.execute = AsyncMock(return_value=result)

    service = RemediationService(db=db)
    request = SimpleNamespace(
        tenant_id=uuid4(), connection_id=connection_id, provider="license"
    )

    resolved = await service._resolve_credentials(request)

    assert resolved["vendor"] == "custom_vendor"
    assert resolved["auth_method"] == "manual"
    assert resolved["connector_config"] == {"default_seat_price_usd": 9.5}
    assert resolved["license_feed"] == [{"user_id": "feed-user-1"}]


@pytest.mark.asyncio
async def test_license_action_manual_fallback_returns_skipped() -> None:
    action = LicenseReclaimSeatAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "custom_vendor",
            "auth_method": "manual",
            "api_key": None,
            "connector_config": {},
            "license_feed": [],
        },
        parameters={},
    )

    with patch(
        "app.modules.optimization.domain.actions.license.base.LicenseAdapter"
    ) as adapter_cls:
        adapter_cls.return_value.revoke_license = AsyncMock(
            side_effect=NotImplementedError("no native revoke")
        )
        result = await action._perform_action("user-9", context)

    assert result.status == ExecutionStatus.SKIPPED
    assert result.error_message is not None
    assert "Manual follow-up required" in result.error_message
