from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.hybrid_connection import HybridConnection
from app.models.platform_connection import PlatformConnection
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.actions import RemediationActionFactory
from app.modules.optimization.domain.actions.base import (
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions.hybrid.base import HybridManualReviewAction
from app.modules.optimization.domain.actions.platform.base import (
    PlatformManualReviewAction,
)
from app.modules.optimization.domain.remediation import RemediationService


@pytest.mark.asyncio
async def test_platform_manual_review_action_builds_typed_credentials() -> None:
    action = PlatformManualReviewAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "datadog",
            "auth_method": "api_key",
            "api_key": "dd_key",
            "api_secret": "dd_secret",
            "connector_config": {"site": "datadoghq.com"},
            "spend_feed": [{"cost_usd": 10.0}],
        },
    )

    result = await action._perform_action("platform-resource-1", context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.action_taken == RemediationAction.MANUAL_REVIEW.value
    assert result.metadata is not None
    assert result.metadata["provider"] == "platform"
    assert result.metadata["vendor"] == "datadog"
    assert result.metadata["auth_method"] == "api_key"


@pytest.mark.asyncio
async def test_hybrid_manual_review_action_builds_typed_credentials() -> None:
    action = HybridManualReviewAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "openstack",
            "auth_method": "api_key",
            "api_key": "hy_key",
            "api_secret": "hy_secret",
            "connector_config": {"auth_url": "https://openstack.example.com/v3"},
            "spend_feed": [{"cost_usd": 20.0}],
        },
    )

    result = await action._perform_action("hybrid-resource-1", context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.action_taken == RemediationAction.MANUAL_REVIEW.value
    assert result.metadata is not None
    assert result.metadata["provider"] == "hybrid"
    assert result.metadata["vendor"] == "openstack"
    assert result.metadata["auth_method"] == "api_key"


def test_action_factory_registers_platform_and_hybrid_manual_review() -> None:
    platform_strategy = RemediationActionFactory.get_strategy(
        "platform", RemediationAction.MANUAL_REVIEW
    )
    hybrid_strategy = RemediationActionFactory.get_strategy(
        "hybrid", RemediationAction.MANUAL_REVIEW
    )

    assert isinstance(platform_strategy, PlatformManualReviewAction)
    assert isinstance(hybrid_strategy, HybridManualReviewAction)


@pytest.mark.asyncio
async def test_remediation_resolve_credentials_includes_platform_wiring() -> None:
    connection_id = uuid4()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        vendor="datadog",
        auth_method="api_key",
        api_key="dd_key",
        api_secret="dd_secret",
        connector_config={"site": "datadoghq.com"},
        spend_feed=[{"cost_usd": 10.0}],
    )
    db.execute = AsyncMock(return_value=result)

    service = RemediationService(db=db)
    request = SimpleNamespace(
        tenant_id=uuid4(), connection_id=connection_id, provider="platform"
    )
    resolved = await service._resolve_credentials(request)

    assert resolved["vendor"] == "datadog"
    assert resolved["auth_method"] == "api_key"
    assert resolved["api_secret"] == "dd_secret"
    assert resolved["connector_config"] == {"site": "datadoghq.com"}
    assert resolved["spend_feed"] == [{"cost_usd": 10.0}]
    assert resolved["region"] == "global"
    assert resolved["connection_id"] == str(connection_id)


@pytest.mark.asyncio
async def test_remediation_resolve_credentials_includes_hybrid_wiring() -> None:
    connection_id = uuid4()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        vendor="openstack",
        auth_method="api_key",
        api_key="hy_key",
        api_secret="hy_secret",
        connector_config={"auth_url": "https://openstack.example.com/v3"},
        spend_feed=[{"cost_usd": 20.0}],
    )
    db.execute = AsyncMock(return_value=result)

    service = RemediationService(db=db)
    request = SimpleNamespace(
        tenant_id=uuid4(), connection_id=connection_id, provider="hybrid"
    )
    resolved = await service._resolve_credentials(request)

    assert resolved["vendor"] == "openstack"
    assert resolved["auth_method"] == "api_key"
    assert resolved["api_secret"] == "hy_secret"
    assert resolved["connector_config"]["auth_url"].startswith("https://")
    assert resolved["spend_feed"] == [{"cost_usd": 20.0}]
    assert resolved["region"] == "global"
    assert resolved["connection_id"] == str(connection_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "connection_model"),
    [
        ("platform", PlatformConnection),
        ("hybrid", HybridConnection),
    ],
)
async def test_create_request_scopes_platform_and_hybrid_connections(
    provider: str, connection_model: type[PlatformConnection] | type[HybridConnection]
) -> None:
    tenant_id = uuid4()
    connection_id = uuid4()
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    service = RemediationService(db=db)
    service.get_by_id = AsyncMock(return_value=SimpleNamespace(id=connection_id))  # type: ignore[method-assign]

    request = await service.create_request(
        tenant_id=tenant_id,
        user_id=uuid4(),
        resource_id="resource-1",
        resource_type="Cloud+ Resource",
        action=RemediationAction.MANUAL_REVIEW,
        estimated_savings=5.0,
        provider=provider,
        connection_id=connection_id,
    )

    service.get_by_id.assert_awaited_once_with(
        connection_model, connection_id, tenant_id
    )
    assert request.provider == provider
    assert request.region == "global"
