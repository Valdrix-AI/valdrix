from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.shared.core.approval_permissions import (
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
    APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    normalize_approval_permissions,
    role_default_approval_permissions,
    user_has_approval_permission,
)


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _one_result(value: object) -> MagicMock:
    result = MagicMock()
    result.one_or_none.return_value = value
    return result


def _rows_result(rows: list[tuple[str]]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def test_normalize_approval_permissions_filters_invalid_values() -> None:
    permissions = normalize_approval_permissions(
        [
            " remediation.approve.nonprod ",
            "REMEDIATION.APPROVE.PROD",
            "unknown.permission",
            "",
        ]
    )
    assert permissions == [
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    ]


def test_role_default_approval_permissions() -> None:
    assert role_default_approval_permissions("owner") == {
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    }
    assert role_default_approval_permissions("admin") == {
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
    }
    assert role_default_approval_permissions("member") == set()


@pytest.mark.asyncio
async def test_user_has_approval_permission_owner_and_admin_short_circuit() -> None:
    db = AsyncMock()

    owner = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="owner")
    admin = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="admin")

    assert await user_has_approval_permission(
        db, owner, APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )
    assert await user_has_approval_permission(
        db, admin, APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
    )
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_user_has_approval_permission_from_scim_group_mappings() -> None:
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="member")

    db.execute.side_effect = [
        _one_result(
            (
                True,
                [
                    {
                        "group": "finops-approvers",
                        "permissions": [APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD],
                    }
                ],
            )
        ),
        _rows_result([("finops-approvers",)]),
    ]

    assert await user_has_approval_permission(
        db, user, APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )


@pytest.mark.asyncio
async def test_user_has_approval_permission_denies_without_matching_group() -> None:
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="member")

    db.execute.side_effect = [
        _one_result(
            (
                True,
                [
                    {
                        "group": "finops-approvers",
                        "permissions": [APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD],
                    }
                ],
            )
        ),
        _rows_result([("readonly-users",)]),
    ]

    assert not await user_has_approval_permission(
        db, user, APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD
    )


@pytest.mark.asyncio
async def test_user_has_approval_permission_denies_when_scim_disabled() -> None:
    db = AsyncMock()
    user = SimpleNamespace(id=uuid4(), tenant_id=uuid4(), role="member")

    db.execute.side_effect = [
        _one_result(
            (
                False,
                [
                    {
                        "group": "finops-approvers",
                        "permissions": [APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD],
                    }
                ],
            )
        ),
    ]

    assert not await user_has_approval_permission(
        db, user, APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD
    )
