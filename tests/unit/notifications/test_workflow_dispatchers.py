from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.notifications.domain.workflows import (
    GenericCIWebhookDispatcher,
    GitHubActionsDispatcher,
    GitLabCIDispatcher,
    get_workflow_dispatchers,
    get_tenant_workflow_dispatchers,
)


def _async_client_cm(client: AsyncMock) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = None
    return cm


@pytest.mark.asyncio
async def test_github_dispatch_success_and_failure() -> None:
    dispatcher = GitHubActionsDispatcher(
        owner="valdrix-ai",
        repo="valdrix",
        workflow_id="remediation.yml",
        ref="main",
        token="ghp_token",
        timeout_seconds=5.0,
    )

    ok_response = MagicMock(status_code=204, text="")
    client = AsyncMock()
    client.post = AsyncMock(return_value=ok_response)
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        ok = await dispatcher.dispatch(
            "policy.block",
            {"tenant_id": "t1", "request_id": "r1", "resource_id": "i-1"},
        )
    assert ok is True

    bad_response = MagicMock(status_code=401, text="unauthorized")
    client.post = AsyncMock(return_value=bad_response)
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        ok = await dispatcher.dispatch("policy.block", {"tenant_id": "t1"})
    assert ok is False


@pytest.mark.asyncio
async def test_gitlab_dispatch_success() -> None:
    dispatcher = GitLabCIDispatcher(
        base_url="https://gitlab.com",
        project_id="123",
        ref="main",
        trigger_token="gl-token",
        timeout_seconds=5.0,
    )
    response = MagicMock(status_code=201, text="")
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=client,
    ):
        ok = await dispatcher.dispatch(
            "remediation.completed",
            {"tenant_id": "t1", "request_id": "r1"},
        )
    assert ok is True
    call_data = client.post.await_args.kwargs["data"]
    assert call_data["variables[VALDRIX_EVENT_TYPE]"] == "remediation.completed"


@pytest.mark.asyncio
async def test_generic_dispatch_validates_allowlist_and_posts() -> None:
    dispatcher = GenericCIWebhookDispatcher(
        url="https://ci.example.com/hooks/valdrix",
        bearer_token="secret-token",
        timeout_seconds=5.0,
    )
    response = MagicMock(status_code=202, text="")
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    settings = SimpleNamespace(
        WEBHOOK_ALLOWED_DOMAINS=["example.com"],
        WEBHOOK_REQUIRE_HTTPS=True,
        WEBHOOK_BLOCK_PRIVATE_IPS=True,
    )
    with (
        patch(
            "app.modules.notifications.domain.workflows.get_settings",
            return_value=settings,
        ),
        patch(
            "app.shared.core.http.get_http_client",
            return_value=client,
        ),
    ):
        ok = await dispatcher.dispatch("policy.escalate", {"tenant_id": "t-1"})

    assert ok is True
    headers = client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_generic_dispatch_rejects_non_allowlisted_host() -> None:
    dispatcher = GenericCIWebhookDispatcher(
        url="https://evil.example.org/hook",
        bearer_token=None,
        timeout_seconds=5.0,
    )
    settings = SimpleNamespace(
        WEBHOOK_ALLOWED_DOMAINS=["example.com"],
        WEBHOOK_REQUIRE_HTTPS=True,
        WEBHOOK_BLOCK_PRIVATE_IPS=True,
    )
    with patch(
        "app.modules.notifications.domain.workflows.get_settings",
        return_value=settings,
    ):
        ok = await dispatcher.dispatch("policy.escalate", {"tenant_id": "t-1"})
    assert ok is False


def test_get_workflow_dispatchers_returns_all_enabled() -> None:
    settings = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=False,
        WORKFLOW_DISPATCH_TIMEOUT_SECONDS=7.0,
        GITHUB_ACTIONS_ENABLED=True,
        GITHUB_ACTIONS_OWNER="valdrix-ai",
        GITHUB_ACTIONS_REPO="valdrix",
        GITHUB_ACTIONS_WORKFLOW_ID="remediation.yml",
        GITHUB_ACTIONS_REF="main",
        GITHUB_ACTIONS_TOKEN="gh-token",
        GITLAB_CI_ENABLED=True,
        GITLAB_CI_BASE_URL="https://gitlab.com",
        GITLAB_CI_PROJECT_ID="123",
        GITLAB_CI_REF="main",
        GITLAB_CI_TRIGGER_TOKEN="gl-token",
        GENERIC_CI_WEBHOOK_ENABLED=True,
        GENERIC_CI_WEBHOOK_URL="https://ci.example.com/hook",
        GENERIC_CI_WEBHOOK_BEARER_TOKEN="ci-token",
    )
    with patch(
        "app.modules.notifications.domain.workflows.get_settings", return_value=settings
    ):
        dispatchers = get_workflow_dispatchers()

    providers = [getattr(d, "provider") for d in dispatchers]
    assert providers == ["github_actions", "gitlab_ci", "generic_ci_webhook"]


def test_get_workflow_dispatchers_skips_incomplete_provider() -> None:
    settings = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=False,
        WORKFLOW_DISPATCH_TIMEOUT_SECONDS=7.0,
        GITHUB_ACTIONS_ENABLED=True,
        GITHUB_ACTIONS_OWNER=None,
        GITHUB_ACTIONS_REPO="valdrix",
        GITHUB_ACTIONS_WORKFLOW_ID="remediation.yml",
        GITHUB_ACTIONS_REF="main",
        GITHUB_ACTIONS_TOKEN="gh-token",
        GITLAB_CI_ENABLED=False,
        GITLAB_CI_BASE_URL="https://gitlab.com",
        GITLAB_CI_PROJECT_ID=None,
        GITLAB_CI_REF="main",
        GITLAB_CI_TRIGGER_TOKEN=None,
        GENERIC_CI_WEBHOOK_ENABLED=False,
        GENERIC_CI_WEBHOOK_URL=None,
        GENERIC_CI_WEBHOOK_BEARER_TOKEN=None,
    )
    with patch(
        "app.modules.notifications.domain.workflows.get_settings", return_value=settings
    ):
        dispatchers = get_workflow_dispatchers()
    assert dispatchers == []


def test_get_workflow_dispatchers_returns_empty_in_strict_mode() -> None:
    settings = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=True,
        WORKFLOW_DISPATCH_TIMEOUT_SECONDS=7.0,
        GITHUB_ACTIONS_ENABLED=True,
        GITHUB_ACTIONS_OWNER="valdrix-ai",
        GITHUB_ACTIONS_REPO="valdrix",
        GITHUB_ACTIONS_WORKFLOW_ID="remediation.yml",
        GITHUB_ACTIONS_REF="main",
        GITHUB_ACTIONS_TOKEN="gh-token",
        GITLAB_CI_ENABLED=True,
        GITLAB_CI_BASE_URL="https://gitlab.com",
        GITLAB_CI_PROJECT_ID="123",
        GITLAB_CI_REF="main",
        GITLAB_CI_TRIGGER_TOKEN="gl-token",
        GENERIC_CI_WEBHOOK_ENABLED=True,
        GENERIC_CI_WEBHOOK_URL="https://ci.example.com/hook",
        GENERIC_CI_WEBHOOK_BEARER_TOKEN="ci-token",
    )
    with patch(
        "app.modules.notifications.domain.workflows.get_settings", return_value=settings
    ):
        dispatchers = get_workflow_dispatchers()
    assert dispatchers == []


@pytest.mark.asyncio
async def test_get_tenant_workflow_dispatchers_builds_from_notification_settings() -> (
    None
):
    db = MagicMock()
    notif = SimpleNamespace(
        workflow_github_enabled=True,
        workflow_github_owner="Valdrix-AI",
        workflow_github_repo="valdrix",
        workflow_github_workflow_id="remediation.yml",
        workflow_github_ref="main",
        workflow_github_token="gh-token",
        workflow_gitlab_enabled=True,
        workflow_gitlab_base_url="https://gitlab.com",
        workflow_gitlab_project_id="123",
        workflow_gitlab_ref="main",
        workflow_gitlab_trigger_token="gl-token",
        workflow_webhook_enabled=True,
        workflow_webhook_url="https://ci.example.com/hook",
        workflow_webhook_bearer_token="ci-token",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = notif
    db.execute = AsyncMock(return_value=result)
    settings = SimpleNamespace(WORKFLOW_DISPATCH_TIMEOUT_SECONDS=9.0)

    with patch(
        "app.modules.notifications.domain.workflows.get_settings", return_value=settings
    ):
        dispatchers = await get_tenant_workflow_dispatchers(
            db, "11111111-1111-1111-1111-111111111111"
        )
    assert [d.provider for d in dispatchers] == [
        "github_actions",
        "gitlab_ci",
        "generic_ci_webhook",
    ]


@pytest.mark.asyncio
async def test_get_tenant_workflow_dispatchers_handles_invalid_tenant() -> None:
    db = MagicMock()
    dispatchers = await get_tenant_workflow_dispatchers(db, "invalid-tenant")
    assert dispatchers == []
