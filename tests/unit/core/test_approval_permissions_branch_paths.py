from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    _load_scim_approval_permissions,
    _load_scim_group_mappings,
    normalize_approval_permissions,
    user_has_approval_permission,
)


def _one_result(value: object) -> MagicMock:
    result = MagicMock()
    result.one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_normalize_approval_permissions_handles_none_and_duplicates() -> None:
    assert normalize_approval_permissions(None) == []
    assert normalize_approval_permissions(
        [
            APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
            APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
        ]
    ) == [APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD]


@pytest.mark.asyncio
async def test_load_scim_group_mappings_handles_missing_row_and_non_list_raw() -> None:
    db = AsyncMock()
    tenant_id = uuid4()
    db.execute.side_effect = [
        _one_result(None),
        _one_result((True, {"group": "approvers"})),
    ]

    assert await _load_scim_group_mappings(db, tenant_id) == []
    assert await _load_scim_group_mappings(db, tenant_id) == []


@pytest.mark.asyncio
async def test_load_scim_approval_permissions_returns_empty_when_user_has_no_groups() -> None:
    db = AsyncMock()
    tenant_id = uuid4()
    user_id = uuid4()

    with (
        patch(
            "app.shared.core.approval_permissions._load_scim_group_mappings",
            new=AsyncMock(return_value=[{"group": "finops", "permissions": []}]),
        ),
        patch(
            "app.shared.core.approval_permissions._load_user_group_names",
            new=AsyncMock(return_value=set()),
        ),
    ):
        assert await _load_scim_approval_permissions(db, tenant_id, user_id) == set()


@pytest.mark.asyncio
async def test_user_has_approval_permission_denies_invalid_required_permission() -> None:
    user = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="member")
    assert not await user_has_approval_permission(AsyncMock(), user, "invalid.permission")


@pytest.mark.asyncio
async def test_user_has_approval_permission_denies_invalid_user_identity_types() -> None:
    user = SimpleNamespace(id="not-a-uuid", tenant_id=uuid4(), role="member")
    assert not await user_has_approval_permission(
        AsyncMock(), user, APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )


@pytest.mark.asyncio
async def test_user_has_approval_permission_logs_and_denies_on_scim_resolution_error() -> None:
    user = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="member")
    db = AsyncMock()

    with (
        patch(
            "app.shared.core.approval_permissions._load_scim_approval_permissions",
            new=AsyncMock(side_effect=RuntimeError("scim lookup failed")),
        ),
        patch("app.shared.core.approval_permissions.logger") as mock_logger,
    ):
        allowed = await user_has_approval_permission(
            db, user, APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
        )

    assert allowed is False
    mock_logger.exception.assert_called_once()
