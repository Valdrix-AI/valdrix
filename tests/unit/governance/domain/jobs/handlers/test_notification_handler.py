
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.governance.domain.jobs.handlers.notifications import NotificationHandler, WebhookRetryHandler
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
    job = BackgroundJob(payload={"message": "alert"})
    
    with patch("app.modules.notifications.domain.get_slack_service", return_value=None):
        result = await handler.execute(job, db)
        assert result["status"] == "skipped"
        assert result["reason"] == "slack_not_configured"

@pytest.mark.asyncio
async def test_notification_execute_success(db):
    handler = NotificationHandler()
    job = BackgroundJob(payload={"message": "alert", "title": "Test Alert"})
    
    mock_service = AsyncMock()
    mock_service.send_alert.return_value = True
    
    with patch("app.modules.notifications.domain.get_slack_service", return_value=mock_service):
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["success"] is True
        mock_service.send_alert.assert_awaited_with(
            title="Test Alert",
            message="alert",
            severity="info"
        )

@pytest.mark.asyncio
async def test_webhook_retry_execute_generic_success(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(payload={
        "url": "https://example.com/webhook",
        "data": {"foo": "bar"}
    })
    
    with patch("httpx.AsyncClient") as MockClient:
        mock_client = MockClient.return_value.__aenter__.return_value
        mock_client.post.return_value = MagicMock(status_code=200)
        
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["status_code"] == 200
        mock_client.post.assert_awaited_with(
            "https://example.com/webhook",
            json={"foo": "bar"},
            headers={},
            timeout=30
        )

@pytest.mark.asyncio
async def test_webhook_retry_execute_paystack(db):
    handler = WebhookRetryHandler()
    job = BackgroundJob(payload={"provider": "paystack"})
    
    with patch("app.modules.reporting.domain.billing.webhook_retry.process_paystack_webhook", new_callable=AsyncMock) as mock_process:
        mock_process.return_value = {"status": "processed"}
        
        result = await handler.execute(job, db)
        
        assert result == {"status": "processed"}
        mock_process.assert_awaited_with(job, db)
