from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.domain.remediation import (
    RemediationAction,
    RemediationService,
)


def _db_stub() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_request_aws_uses_scoped_connection_region_when_hint_is_global() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connection_id = uuid4()
    db = _db_stub()
    service = RemediationService(db=db, region="global")
    scoped_connection = SimpleNamespace(region="eu-west-1")

    service.get_by_id = AsyncMock(return_value=scoped_connection)  # type: ignore[method-assign]

    with (
        patch(
            "app.modules.optimization.domain.remediation.get_connection_model",
            return_value=object(),
        ),
        patch.object(
            service,
            "_build_system_policy_context",
            new=AsyncMock(return_value={}),
        ),
    ):
        request = await service.create_request(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id="i-123",
            resource_type="EC2 Instance",
            action=RemediationAction.STOP_INSTANCE,
            estimated_savings=12.3,
            provider="aws",
            connection_id=connection_id,
        )

    assert request.region == "eu-west-1"


@pytest.mark.asyncio
async def test_preview_policy_input_aws_uses_scoped_connection_region_when_hint_is_global() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    connection_id = uuid4()
    db = _db_stub()
    service = RemediationService(db=db, region="global")
    scoped_connection = SimpleNamespace(region="ap-southeast-2")
    captured: dict[str, str] = {}

    service.get_by_id = AsyncMock(return_value=scoped_connection)  # type: ignore[method-assign]

    async def _fake_preview(request: object, _tenant_id: object) -> dict[str, object]:
        captured["region"] = str(getattr(request, "region", ""))
        return {
            "decision": "warn",
            "summary": "test preview",
            "rule_hits": [],
            "tier": "pro",
            "config": {},
        }

    service.preview_policy = AsyncMock(side_effect=_fake_preview)  # type: ignore[method-assign]

    with (
        patch(
            "app.modules.optimization.domain.remediation.get_connection_model",
            return_value=object(),
        ),
        patch.object(
            service,
            "_build_system_policy_context",
            new=AsyncMock(return_value={}),
        ),
    ):
        preview = await service.preview_policy_input(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id="i-456",
            resource_type="GPU Compute",
            action=RemediationAction.TERMINATE_INSTANCE,
            provider="aws",
            connection_id=connection_id,
        )

    assert captured["region"] == "ap-southeast-2"
    assert preview["decision"] == "warn"


@pytest.mark.asyncio
async def test_create_request_non_aws_forces_global_region() -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    db = _db_stub()
    service = RemediationService(db=db, region="us-east-1")

    with patch.object(
        service,
        "_build_system_policy_context",
        new=AsyncMock(return_value={}),
    ):
        request = await service.create_request(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id="vm-001",
            resource_type="VM Instance",
            action=RemediationAction.STOP_INSTANCE,
            estimated_savings=7.5,
            provider="azure",
        )

    assert request.region == "global"


@pytest.mark.asyncio
async def test_resolve_aws_region_hint_falls_back_to_config_default() -> None:
    db = _db_stub()
    service = RemediationService(db=db, region="global")

    with patch(
        "app.modules.optimization.domain.remediation.get_settings",
        return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-north-1"),
    ):
        resolved = await service._resolve_aws_region_hint()

    assert resolved == "eu-north-1"
