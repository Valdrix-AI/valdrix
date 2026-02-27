from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions.base import (
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions.hybrid.base import HybridManualReviewAction
from app.modules.optimization.domain.actions.license.base import LicenseReclaimSeatAction
from app.modules.optimization.domain.actions.platform.base import PlatformManualReviewAction
from app.shared.core.credentials import HybridCredentials, LicenseCredentials, PlatformCredentials
from app.shared.core.pricing import FeatureFlag


def _context(credentials: dict[str, object] | None = None) -> RemediationContext:
    return RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials=credentials,
        parameters={},
    )


@pytest.mark.asyncio
async def test_license_base_methods_and_build_credentials_guards() -> None:
    action = LicenseReclaimSeatAction()

    assert action.required_feature == FeatureFlag.CLOUD_PLUS_CONNECTORS
    assert await action.validate(" user-1 ", _context()) is True
    assert await action.validate("   ", _context()) is False
    assert await action.create_backup("user-1", _context()) is None

    typed = LicenseCredentials(vendor="google_workspace", auth_method="manual")
    assert action._build_credentials(typed) is typed

    with pytest.raises(ValueError, match="Invalid license credentials payload"):
        action._build_credentials(object())


@pytest.mark.asyncio
async def test_license_action_failed_status_when_revoke_returns_false() -> None:
    action = LicenseReclaimSeatAction()
    context = _context(
        {
            "vendor": "google_workspace",
            "auth_method": "oauth",
            "connector_config": {},
            "license_feed": [],
        }
    )

    with patch("app.modules.optimization.domain.actions.license.base.LicenseAdapter") as adapter_cls:
        adapter_cls.return_value.revoke_license = AsyncMock(return_value=False)
        result = await action._perform_action("user-404", context)

    assert result.status == ExecutionStatus.FAILED
    assert result.action_taken == RemediationAction.RECLAIM_LICENSE_SEAT.value
    assert result.error_message is not None
    assert "failed" in result.error_message.lower()


@pytest.mark.asyncio
async def test_license_action_generic_exception_returns_failed() -> None:
    action = LicenseReclaimSeatAction()
    context = _context(
        {
            "vendor": "google_workspace",
            "auth_method": "oauth",
            "connector_config": {},
            "license_feed": [],
        }
    )

    with patch(
        "app.modules.optimization.domain.actions.license.base.LicenseAdapter",
        side_effect=RuntimeError("adapter init failed"),
    ):
        result = await action._perform_action("user-1", context)

    assert result.status == ExecutionStatus.FAILED
    assert result.error_message == "adapter init failed"


@pytest.mark.asyncio
async def test_hybrid_base_methods_and_credential_build_guards() -> None:
    action = HybridManualReviewAction()

    assert action.required_feature == FeatureFlag.CLOUD_PLUS_CONNECTORS
    assert await action.validate("hy-1", _context()) is True
    assert await action.validate("", _context()) is False
    assert await action.create_backup("hy-1", _context()) is None

    typed = HybridCredentials(vendor="openstack", auth_method="manual")
    assert action._build_credentials(typed) is typed

    with pytest.raises(ValueError, match="Invalid hybrid credentials payload"):
        action._build_credentials(object())


@pytest.mark.asyncio
async def test_platform_base_methods_and_credential_build_guards() -> None:
    action = PlatformManualReviewAction()

    assert action.required_feature == FeatureFlag.CLOUD_PLUS_CONNECTORS
    assert await action.validate("pf-1", _context()) is True
    assert await action.validate("", _context()) is False
    assert await action.create_backup("pf-1", _context()) is None

    typed = PlatformCredentials(vendor="datadog", auth_method="manual")
    assert action._build_credentials(typed) is typed

    with pytest.raises(ValueError, match="Invalid platform credentials payload"):
        action._build_credentials(object())

