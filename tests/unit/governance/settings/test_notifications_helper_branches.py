from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status

from app.modules.governance.api.v1.settings import notifications as notifications_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def test_normalize_acceptance_details_stringifies_non_scalar_values() -> None:
    raw = {
        "ok_str": "value",
        "ok_int": 5,
        "ok_float": 1.5,
        "ok_bool": True,
        "ok_list": [1, "two"],
        "obj": {"nested": "value"},
        "none_value": None,
    }

    normalized = notifications_api._normalize_acceptance_details(raw)

    assert normalized["ok_str"] == "value"
    assert normalized["ok_int"] == 5
    assert normalized["ok_float"] == 1.5
    assert normalized["ok_bool"] is True
    assert normalized["ok_list"] == ["1", "two"]
    assert normalized["obj"] == "{'nested': 'value'}"
    assert "none_value" not in normalized


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (200, 200),
        (200.0, 200),
        (" 404 ", 404),
        (200.5, None),
        ("abc", None),
    ],
)
def test_coerce_status_code_paths(value: object, expected: int | None) -> None:
    assert notifications_api._coerce_status_code(value) == expected


@pytest.mark.asyncio
async def test_run_workflow_connectivity_test_requires_tenant() -> None:
    user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=None,
        email="admin@example.com",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    result = await notifications_api._run_workflow_connectivity_test(
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result.success is False
    assert result.status_code == status.HTTP_403_FORBIDDEN
    assert "Tenant context required" in result.message


@pytest.mark.asyncio
async def test_run_workflow_connectivity_test_blocks_tier_without_feature() -> None:
    user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )

    result = await notifications_api._run_workflow_connectivity_test(
        current_user=user,
        db=SimpleNamespace(),
    )

    assert result.success is False
    assert result.status_code == status.HTTP_403_FORBIDDEN
    assert "incident_integrations" in result.message


@pytest.mark.asyncio
async def test_run_workflow_connectivity_test_all_dispatchers_fail() -> None:
    user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@example.com",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    dispatcher_exception = AsyncMock()
    dispatcher_exception.provider = "github_actions"
    dispatcher_exception.dispatch.side_effect = RuntimeError("boom")
    dispatcher_false = AsyncMock()
    dispatcher_false.provider = "gitlab_ci"
    dispatcher_false.dispatch.return_value = False

    with patch(
        "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
        new=AsyncMock(return_value=[dispatcher_exception, dispatcher_false]),
    ):
        result = await notifications_api._run_workflow_connectivity_test(
            current_user=user,
            db=SimpleNamespace(),
        )

    assert result.success is False
    assert result.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert result.details["total_targets"] == 2
    assert result.details["successful_targets"] == 0
    assert result.details["provider_results"] == [
        "github_actions:failed",
        "gitlab_ci:failed",
    ]
