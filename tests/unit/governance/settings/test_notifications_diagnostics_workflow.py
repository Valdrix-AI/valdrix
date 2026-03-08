from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.notification_settings import NotificationSettings
from app.models.remediation_settings import RemediationSettings
from app.shared.core.config import Settings
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_missing_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = None
    mock_settings.SLACK_CHANNEL_ID = None

    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch("app.shared.core.config.get_settings", return_value=mock_settings),
    ):
        response = await async_client.get(
            "/api/v1/settings/notifications/policy-diagnostics"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["has_activeops_settings"] is False
    assert data["has_notification_settings"] is False
    assert data["slack"]["ready"] is False
    assert "missing_slack_bot_token" in data["slack"]["reasons"]
    assert "missing_slack_channel_target" in data["slack"]["reasons"]
    assert data["jira"]["ready"] is False
    assert "tenant_jira_disabled" in data["jira"]["reasons"]


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_ready(
    async_client: AsyncClient,
    db,
    app,
    make_current_user,
    override_current_user,
) -> None:
    tenant_id = uuid.uuid4()
    admin = make_current_user(tier=PricingTier.PRO, tenant_id=tenant_id)
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            slack_channel_override="#finops-alerts",
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    db.add(
        RemediationSettings(
            tenant_id=tenant_id,
            policy_enabled=True,
            policy_violation_notify_slack=True,
            policy_violation_notify_jira=True,
        )
    )
    await db.commit()

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"

    with (
        override_current_user(app, admin),
        patch("app.shared.core.config.get_settings", return_value=mock_settings),
    ):
        response = await async_client.get(
            "/api/v1/settings/notifications/policy-diagnostics"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["policy_enabled"] is True
    assert data["slack"]["ready"] is True
    assert data["slack"]["channel_source"] == "tenant_override"
    assert data["jira"]["ready"] is True
    assert data["jira"]["feature_allowed_by_tier"] is True


@pytest.mark.asyncio
async def test_policy_notification_diagnostics_jira_tier_blocked(
    async_client: AsyncClient,
    db,
    app,
    make_current_user,
    override_current_user,
) -> None:
    tenant_id = uuid.uuid4()
    admin = make_current_user(tier=PricingTier.GROWTH, tenant_id=tenant_id)
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    db.add(
        RemediationSettings(
            tenant_id=tenant_id,
            policy_enabled=True,
            policy_violation_notify_jira=True,
        )
    )
    await db.commit()

    mock_settings = Settings()
    mock_settings.SLACK_BOT_TOKEN = "xoxb-test"
    mock_settings.SLACK_CHANNEL_ID = "C12345"

    with (
        override_current_user(app, admin),
        patch("app.shared.core.config.get_settings", return_value=mock_settings),
    ):
        response = await async_client.get(
            "/api/v1/settings/notifications/policy-diagnostics"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["jira"]["ready"] is False
    assert data["jira"]["feature_allowed_by_tier"] is False
    assert "tier_missing_incident_integrations_feature" in data["jira"]["reasons"]


@pytest.mark.asyncio
async def test_update_notification_settings_with_workflow_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_workflow_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_workflow_payload(),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow_github_enabled"] is True
    assert data["workflow_has_github_token"] is True
    assert data["workflow_gitlab_enabled"] is True
    assert data["workflow_has_gitlab_trigger_token"] is True
    assert data["workflow_webhook_enabled"] is True
    assert data["workflow_has_webhook_bearer_token"] is True


@pytest.mark.asyncio
async def test_update_notification_settings_workflow_requires_incident_tier(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_workflow_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.GROWTH)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_workflow_payload(
                workflow_gitlab_enabled=False,
                workflow_webhook_enabled=False,
            ),
        )

    assert response.status_code == 403
    assert "incident_integrations" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notification_settings_workflow_missing_fields_returns_422(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_workflow_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_workflow_payload(
                workflow_github_workflow_id=None,
                workflow_gitlab_enabled=False,
                workflow_webhook_enabled=False,
            ),
        )

    assert response.status_code == 422
    assert "missing required fields" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_workflow_notification_success(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    workflow_dispatcher = AsyncMock()
    workflow_dispatcher.dispatch.return_value = True

    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch(
            "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
            new=AsyncMock(return_value=[workflow_dispatcher]),
        ),
    ):
        response = await async_client.post(
            "/api/v1/settings/notifications/test-workflow"
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_test_workflow_notification_missing_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch(
            "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
            new=AsyncMock(return_value=[]),
        ),
    ):
        response = await async_client.post(
            "/api/v1/settings/notifications/test-workflow"
        )

    assert response.status_code == 400
    assert "No workflow integration is configured" in response.json()["error"]
