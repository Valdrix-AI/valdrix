from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.optimization.domain.actions.base import (
    ExecutionStatus,
    RemediationContext,
)
from app.modules.optimization.domain.actions import RemediationActionFactory
from app.modules.optimization.domain.actions.saas.github import GitHubRevokeSeatAction
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.core.credentials import SaaSCredentials
from app.models.remediation import RemediationAction


@pytest.mark.asyncio
async def test_saas_github_action_builds_typed_credentials_from_dict() -> None:
    action = GitHubRevokeSeatAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "github",
            "auth_method": "api_key",
            "api_key": "ghp_test_token",
            "connector_config": {"github_org": "valdrix-org"},
            "spend_feed": [],
        },
    )

    mock_response = MagicMock()
    mock_response.status_code = 204

    mock_client = AsyncMock()
    mock_client.delete = AsyncMock(return_value=mock_response)
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch(
        "app.modules.optimization.domain.actions.saas.github.httpx.AsyncClient",
        return_value=mock_cm,
    ):
        result = await action._perform_action("octocat", context)

    assert result.status == ExecutionStatus.SUCCESS
    assert result.metadata is not None
    assert result.metadata["organization"] == "valdrix-org"


@pytest.mark.asyncio
async def test_saas_github_action_missing_org_returns_failed() -> None:
    action = GitHubRevokeSeatAction()
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={
            "vendor": "github",
            "auth_method": "api_key",
            "api_key": "ghp_test_token",
            "connector_config": {},
        },
    )

    result = await action._perform_action("octocat", context)
    assert result.status == ExecutionStatus.FAILED
    assert result.error_message is not None
    assert "github_org" in result.error_message


@pytest.mark.asyncio
async def test_remediation_resolve_credentials_includes_saas_wiring() -> None:
    connection_id = uuid4()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        vendor="stripe",
        auth_method="api_key",
        api_key="sk_live_test",
        connector_config={"instance_url": "https://api.stripe.com"},
        spend_feed=[{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 10.0}],
    )
    db.execute = AsyncMock(return_value=result)

    service = RemediationService(db=db)
    request = SimpleNamespace(
        tenant_id=uuid4(), connection_id=connection_id, provider="saas"
    )

    resolved = await service._resolve_credentials(request)

    assert resolved["vendor"] == "stripe"
    assert resolved["auth_method"] == "api_key"
    assert resolved["connector_config"]["instance_url"] == "https://api.stripe.com"
    assert len(resolved["spend_feed"]) == 1
    assert resolved["region"] == "global"
    assert resolved["connection_id"] == str(connection_id)


def test_saas_credentials_support_connector_fields() -> None:
    creds = SaaSCredentials(
        platform="github",
        api_key="ghp_test_token",
        auth_method="api_key",
        connector_config={"github_org": "valdrix-org"},
        spend_feed=[{"cost_usd": 1.0}],
    )
    assert creds.auth_method == "api_key"
    assert creds.connector_config["github_org"] == "valdrix-org"
    assert creds.spend_feed[0]["cost_usd"] == 1.0


@pytest.mark.asyncio
async def test_saas_manual_review_strategy_is_registered() -> None:
    strategy = RemediationActionFactory.get_strategy("saas", RemediationAction.MANUAL_REVIEW)
    context = RemediationContext(
        tenant_id=uuid4(),
        region="global",
        tier="pro",
        credentials={"vendor": "stripe"},
    )

    result = await strategy.execute("subscription-1", context)
    assert result.status == ExecutionStatus.SUCCESS
    assert result.metadata is not None
    assert result.metadata["provider"] == "saas"
