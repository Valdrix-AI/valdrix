import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from types import SimpleNamespace
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.notifications import (
    NotificationHandler,
    WebhookRetryHandler,
)
from app.models.background_job import BackgroundJob


@pytest.mark.asyncio
async def test_notification_execute_message_required(db):
    handler = NotificationHandler()
    job = BackgroundJob(payload={})

    with pytest.raises(ValueError, match="message required"):
        await handler.execute(job, db)


@pytest.mark.asyncio
async def test_notification_execute_skipped_no_service(db):
    handler = NotificationHandler()
    job = BackgroundJob(payload={"message": "alert"}, tenant_id=uuid4())

    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new_callable=AsyncMock,
        return_value=None,
    ):
        result = await handler.execute(job, db)
        assert result["status"] == "skipped"
        assert result["reason"] == "slack_not_configured"


@pytest.mark.asyncio
async def test_notification_execute_success(db):
    handler = NotificationHandler()
    job = BackgroundJob(
        payload={"message": "alert", "title": "Test Alert"},
        tenant_id=uuid4(),
    )

    mock_service = AsyncMock()
    mock_service.send_alert.return_value = True

    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new_callable=AsyncMock,
        return_value=mock_service,
    ):
        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["success"] is True
        mock_service.send_alert.assert_awaited_with(
            title="Test Alert", message="alert", severity="info"
        )


@pytest.mark.asyncio
async def test_notification_execute_non_tenant_fallback_service(db):
    handler = NotificationHandler()
    job = BackgroundJob(
        payload={"message": "alert", "title": "System Alert"}, tenant_id=None
    )

    mock_service = AsyncMock()
    mock_service.send_alert.return_value = True

    with (
        patch(
            "app.modules.notifications.domain.get_slack_service",
            return_value=mock_service,
        ),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new_callable=AsyncMock,
        ) as tenant_service,
    ):
        result = await handler.execute(job, db)

    tenant_service.assert_not_awaited()
    assert result["status"] == "completed"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_webhook_retry_execute_generic_success(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(
        payload={"url": "https://example.com/webhook", "data": {"foo": "bar"}}
    )

    with (
        patch("app.shared.core.http.get_http_client") as MockGetClient,
        patch(
            "app.modules.governance.domain.jobs.handlers.notifications.get_settings",
            return_value=SimpleNamespace(
                WEBHOOK_ALLOWED_DOMAINS=["example.com"],
                WEBHOOK_REQUIRE_HTTPS=True,
                WEBHOOK_BLOCK_PRIVATE_IPS=True,
            ),
        ),
    ):
        mock_client = MockGetClient.return_value
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))

        result = await handler.execute(job, db)

        assert result["status"] == "completed"
        assert result["status_code"] == 200
        mock_client.post.assert_awaited_with(
            "https://example.com/webhook",
            json={"foo": "bar"},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )


@pytest.mark.asyncio
async def test_webhook_retry_execute_generic_rejects_private_ip(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(
        payload={"url": "https://127.0.0.1/internal", "data": {"foo": "bar"}}
    )

    with patch(
        "app.modules.governance.domain.jobs.handlers.notifications.get_settings",
        return_value=SimpleNamespace(
            WEBHOOK_ALLOWED_DOMAINS=["example.com"],
            WEBHOOK_REQUIRE_HTTPS=True,
            WEBHOOK_BLOCK_PRIVATE_IPS=True,
        ),
    ):
        with pytest.raises(ValueError, match="private or link-local"):
            await handler.execute(job, db)


@pytest.mark.asyncio
async def test_webhook_retry_execute_generic_rejects_non_json_content_type(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(
        payload={
            "url": "https://example.com/webhook",
            "data": {"foo": "bar"},
            "headers": {"Content-Type": "text/plain"},
        }
    )

    with patch(
        "app.modules.governance.domain.jobs.handlers.notifications.get_settings",
        return_value=SimpleNamespace(
            WEBHOOK_ALLOWED_DOMAINS=["example.com"],
            WEBHOOK_REQUIRE_HTTPS=True,
            WEBHOOK_BLOCK_PRIVATE_IPS=True,
        ),
    ):
        with pytest.raises(ValueError, match="content-type"):
            await handler.execute(job, db)


@pytest.mark.asyncio
async def test_webhook_retry_execute_paystack(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(payload={"provider": "paystack"})

    with patch(
        "app.modules.billing.domain.billing.webhook_retry.process_paystack_webhook",
        new_callable=AsyncMock,
    ) as mock_process:
        mock_process.return_value = {"status": "processed"}

        result = await handler.execute(job, db)

        assert result == {"status": "processed"}
        mock_process.assert_awaited_with(job, db)
