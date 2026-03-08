from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.notification_settings import NotificationSettings
from app.modules.governance.api.v1.settings.notifications import (
    NotificationSettingsUpdate,
)
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_update_notification_settings_with_jira_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_jira_payload,
) -> None:
    admin = make_current_user(tier=PricingTier.PRO)

    with override_current_user(app, admin):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_jira_payload(slack_channel_override="#ops"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["jira_enabled"] is True
    assert data["jira_project_key"] == "FINOPS"
    assert data["has_jira_api_token"] is True


@pytest.mark.asyncio
async def test_update_notification_settings_jira_requires_incident_tier(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_jira_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.GROWTH)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_jira_payload(),
        )

    assert response.status_code == 403
    assert "incident_integrations" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notification_settings_rejects_unsafe_jira_base_url(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_jira_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_jira_payload(jira_base_url="https://127.0.0.1"),
        )

    assert response.status_code == 422
    assert "jira_base_url is invalid" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notification_settings_teams_requires_incident_tier(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_teams_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.GROWTH)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_teams_payload(),
        )

    assert response.status_code == 403
    assert "incident_integrations" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notification_settings_teams_missing_fields_returns_422(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_teams_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_teams_payload(teams_webhook_url=None),
        )

    assert response.status_code == 422
    assert "teams_webhook_url" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_teams_notification_success(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    mock_teams = AsyncMock()
    mock_teams.send_alert.return_value = True

    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch(
            "app.modules.notifications.domain.get_tenant_teams_service",
            new=AsyncMock(return_value=mock_teams),
        ),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_test_teams_notification_missing_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch(
            "app.modules.notifications.domain.get_tenant_teams_service",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")

    assert response.status_code == 400
    assert "Teams is not configured" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_teams_notification_requires_incident_tier(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.GROWTH)):
        response = await async_client.post("/api/v1/settings/notifications/test-teams")

    assert response.status_code == 403
    assert "incident_integrations" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_teams_notification_failure_and_exception(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    admin = make_current_user(tier=PricingTier.PRO)

    with override_current_user(app, admin):
        mock_teams = AsyncMock()
        mock_teams.send_alert.return_value = False
        with patch(
            "app.modules.notifications.domain.get_tenant_teams_service",
            new=AsyncMock(return_value=mock_teams),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-teams"
            )
            assert response.status_code == 500
            assert "Failed to send Teams notification" in response.json()["error"]

        mock_teams = AsyncMock()
        mock_teams.send_alert.side_effect = RuntimeError("teams boom")
        with patch(
            "app.modules.notifications.domain.get_tenant_teams_service",
            new=AsyncMock(return_value=mock_teams),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-teams"
            )
            assert response.status_code == 500
            assert "Teams test failed" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_jira_notification_success(
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
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
    )
    await db.commit()

    mock_jira = AsyncMock()
    mock_jira.create_issue.return_value = True

    with (
        override_current_user(app, admin),
        patch(
            "app.modules.notifications.domain.jira.JiraService",
            return_value=mock_jira,
        ),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_test_jira_notification_missing_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")

    assert response.status_code == 400
    assert "Jira is not configured" in response.json()["error"]


def test_notification_settings_update_rejects_token_and_clear_flag() -> None:
    with pytest.raises(
        ValueError, match="Provide jira_api_token or clear_jira_api_token"
    ):
        _ = NotificationSettingsUpdate(
            jira_api_token="jira_token_value_123",
            clear_jira_api_token=True,
        )
    with pytest.raises(
        ValueError, match="Provide teams_webhook_url or clear_teams_webhook_url"
    ):
        _ = NotificationSettingsUpdate(
            teams_webhook_url="https://example.webhook.office.com/abc",
            clear_teams_webhook_url=True,
        )
    with pytest.raises(
        ValueError, match="Provide workflow_github_token or clear_workflow_github_token"
    ):
        _ = NotificationSettingsUpdate(
            workflow_github_token="gh_token_value_123",
            clear_workflow_github_token=True,
        )
    with pytest.raises(
        ValueError,
        match="Provide workflow_gitlab_trigger_token or clear_workflow_gitlab_trigger_token",
    ):
        _ = NotificationSettingsUpdate(
            workflow_gitlab_trigger_token="gl_token_value_123",
            clear_workflow_gitlab_trigger_token=True,
        )
    with pytest.raises(
        ValueError,
        match="Provide workflow_webhook_bearer_token or clear_workflow_webhook_bearer_token",
    ):
        _ = NotificationSettingsUpdate(
            workflow_webhook_bearer_token="webhook_token_value_123",
            clear_workflow_webhook_bearer_token=True,
        )


@pytest.mark.asyncio
async def test_update_notification_settings_clear_jira_token(
    async_client: AsyncClient,
    db,
    app,
    make_current_user,
    override_current_user,
    build_notification_payload,
) -> None:
    tenant_id = uuid.uuid4()
    admin = make_current_user(tier=PricingTier.PRO, tenant_id=tenant_id)
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            jira_enabled=False,
            jira_api_token="jira_token_value_123",
        )
    )
    await db.commit()

    with override_current_user(app, admin):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_notification_payload(
                jira_enabled=False,
                clear_jira_api_token=True,
            ),
        )

    assert response.status_code == 200
    assert response.json()["has_jira_api_token"] is False


@pytest.mark.asyncio
async def test_update_notification_settings_jira_missing_fields_returns_422(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_jira_payload,
) -> None:
    with override_current_user(app, make_current_user(tier=PricingTier.PRO)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_jira_payload(
                jira_email=None,
                jira_api_token=None,
            ),
        )

    assert response.status_code == 422
    assert "missing required fields" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_jira_notification_requires_tenant(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(
        app,
        make_current_user(tier=PricingTier.PRO, tenant_id=None),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-jira")

    assert response.status_code == 403
    assert "Tenant context required" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_jira_notification_failure_and_exception(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    admin = make_current_user(tier=PricingTier.PRO)

    with override_current_user(app, admin):
        mock_jira = AsyncMock()
        mock_jira.create_issue.return_value = False
        with patch(
            "app.modules.notifications.domain.get_tenant_jira_service",
            return_value=mock_jira,
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-jira"
            )
            assert response.status_code == 500
            assert "Failed to create Jira test issue" in response.json()["error"]

        mock_jira = AsyncMock()
        mock_jira.create_issue.side_effect = RuntimeError("jira boom")
        with patch(
            "app.modules.notifications.domain.get_tenant_jira_service",
            return_value=mock_jira,
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-jira"
            )
            assert response.status_code == 500
            assert "Jira test failed" in response.json()["error"]
