from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.notification_settings import NotificationSettings
from app.shared.core.auth import UserRole


@pytest.mark.asyncio
async def test_get_notification_settings_creates_default(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(app, make_current_user(role=UserRole.ADMIN)):
        response = await async_client.get("/api/v1/settings/notifications")

    assert response.status_code == 200
    assert response.json()["slack_enabled"] is True


@pytest.mark.asyncio
async def test_update_notification_settings(
    async_client: AsyncClient,
    db,
    app,
    make_current_user,
    override_current_user,
    build_notification_payload,
) -> None:
    admin = make_current_user(role=UserRole.ADMIN)
    db.add(
        NotificationSettings(
            tenant_id=admin.tenant_id,
            slack_enabled=True,
            digest_schedule="daily",
        )
    )
    await db.commit()

    with override_current_user(app, admin):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_notification_payload(
                slack_enabled=False,
                digest_schedule="weekly",
            ),
        )

    assert response.status_code == 200
    assert response.json()["slack_enabled"] is False


@pytest.mark.asyncio
async def test_update_notification_settings_creates_if_missing(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_notification_payload,
) -> None:
    admin = make_current_user(role=UserRole.ADMIN, email="creator@valdrics.io")

    with override_current_user(app, admin):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_notification_payload(
                slack_channel_override="#alerts",
                digest_schedule="weekly",
                digest_hour=7,
                digest_minute=15,
                alert_on_budget_warning=False,
                alert_on_zombie_detected=False,
            ),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["slack_channel_override"] == "#alerts"
    assert data["digest_schedule"] == "weekly"


@pytest.mark.asyncio
async def test_test_slack_notification(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True

    with (
        override_current_user(app, make_current_user(role=UserRole.ADMIN)),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=mock_slack),
        ),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_test_slack_notification_missing_config(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with (
        override_current_user(app, make_current_user(role=UserRole.ADMIN)),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ),
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")

    assert response.status_code == 400
    assert "Slack is not configured" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_slack_notification_uses_override(
    async_client: AsyncClient,
    db,
    app,
    make_current_user,
    override_current_user,
) -> None:
    tenant_id = uuid.uuid4()
    admin = make_current_user(role=UserRole.ADMIN, tenant_id=tenant_id)
    db.add(
        NotificationSettings(
            tenant_id=tenant_id,
            slack_enabled=True,
            slack_channel_override="#override-channel",
            digest_schedule="daily",
            digest_hour=9,
            digest_minute=0,
            alert_on_budget_warning=True,
            alert_on_budget_exceeded=True,
            alert_on_zombie_detected=True,
        )
    )
    await db.commit()

    mock_slack = AsyncMock()
    mock_slack.send_alert.return_value = True

    with (
        override_current_user(app, admin),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=mock_slack),
        ) as mock_get_tenant,
    ):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")

    assert response.status_code == 200
    mock_get_tenant.assert_awaited_once_with(db, tenant_id)


@pytest.mark.asyncio
async def test_test_slack_notification_failure_and_exception(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    admin = make_current_user(role=UserRole.ADMIN)

    with override_current_user(app, admin):
        mock_slack = AsyncMock()
        mock_slack.send_alert.return_value = False
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=mock_slack),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-slack"
            )
            assert response.status_code == 500
            assert "Failed to send Slack notification" in response.json()["error"]

        mock_slack = AsyncMock()
        mock_slack.send_alert.side_effect = RuntimeError("boom")
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=mock_slack),
        ):
            response = await async_client.post(
                "/api/v1/settings/notifications/test-slack"
            )
            assert response.status_code == 500
            assert "Slack test failed" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notifications_requires_admin(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
    build_notification_payload,
) -> None:
    with override_current_user(app, make_current_user(role=UserRole.MEMBER)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json=build_notification_payload(),
        )

    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["error"]


@pytest.mark.asyncio
async def test_test_slack_notification_requires_admin(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(app, make_current_user(role=UserRole.MEMBER)):
        response = await async_client.post("/api/v1/settings/notifications/test-slack")

    assert response.status_code == 403
    assert "Insufficient permissions" in response.json()["error"]


@pytest.mark.asyncio
async def test_update_notification_settings_validation_failure(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(app, make_current_user(role=UserRole.ADMIN)):
        response = await async_client.put(
            "/api/v1/settings/notifications",
            json={
                "slack_enabled": True,
                "slack_channel_override": "invalid!",
                "digest_schedule": "monthly",
                "digest_hour": 25,
                "digest_minute": 70,
                "alert_on_budget_warning": True,
                "alert_on_budget_exceeded": True,
                "alert_on_zombie_detected": True,
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
