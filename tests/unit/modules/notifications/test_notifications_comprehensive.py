"""
Comprehensive tests for Notifications module (Email & Slack services).
Covers actual service methods: send_carbon_alert, send_alert, etc.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid

from app.modules.notifications.domain.email_service import EmailService
from app.modules.notifications.domain.slack import SlackService


@pytest.fixture
def email_service():
    """Create EmailService instance with dummy credentials."""
    return EmailService(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="test_user",
        smtp_password="test_password",
        from_email="noreply@example.com"
    )


@pytest.fixture
def slack_service():
    """Create SlackService instance with dummy credentials."""
    return SlackService(
        bot_token="xoxb-test-token",
        channel_id="C12345678"
    )


class TestEmailService:
    """Test EmailService methods."""

    @pytest.mark.asyncio
    async def test_send_carbon_alert(self, email_service):
        """Test sending a carbon alert."""
        with patch('app.modules.notifications.domain.email_service.smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock() # SMTP is sync context manager in the code!
            mock_smtp.return_value.__enter__.return_value = mock_server
            
            budget_status = {
                "alert_status": "exceeded",
                "current_usage_kg": 150.0,
                "budget_kg": 100.0,
                "usage_percent": 150.0,
                "recommendations": ["Reduce usage"]
            }
            
            result = await email_service.send_carbon_alert(
                recipients=["user@example.com"],
                budget_status=budget_status
            )
            
            assert result is True
            mock_server.sendmail.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_carbon_alert_failure(self, email_service):
        """Test handling of email send failure."""
        with patch('app.modules.notifications.domain.email_service.smtplib.SMTP') as mock_smtp:
            mock_smtp.side_effect = Exception("SMTP connection failed")
            
            result = await email_service.send_carbon_alert(
                recipients=["user@example.com"],
                budget_status={}
            )
            
            assert result is False

    @pytest.mark.asyncio
    async def test_send_dunning_notification(self, email_service):
        """Test sending payment failure notification."""
        with patch('app.modules.notifications.domain.email_service.smtplib.SMTP') as mock_smtp:
            mock_server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = mock_server

            result = await email_service.send_dunning_notification(
                to_email="user@example.com",
                attempt=1,
                max_attempts=3,
                next_retry_date=datetime.now(),
                tier="pro"
            )

            assert result is True
            mock_server.sendmail.assert_called_once()


class TestSlackService:
    """Test SlackService methods."""

    @pytest.mark.asyncio
    async def test_send_alert(self, slack_service):
        """Test sending an alert."""
        # SlackService uses AsyncWebClient.chat_postMessage
        # It mocks self.client instance logic.
        
        # We can patch the client instance on the fixture
        slack_service.client = AsyncMock()
        slack_service.client.chat_postMessage = AsyncMock()

        result = await slack_service.send_alert(
            title="Test Alert",
            message="Something happened",
            severity="warning"
        )

        assert result is True
        slack_service.client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_rate_limit(self, slack_service):
        """Test rate limit handling (mocking SlackApiError)."""
        from slack_sdk.errors import SlackApiError
        
        slack_service.client = AsyncMock()
        
        # Mock response object
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "0"}
        mock_response.get.side_effect = lambda k, d=None: "ratelimited" if k == "error" else d
        
        # First call fails with ratelimit, second succeeds
        slack_service.client.chat_postMessage.side_effect = [
            SlackApiError(message="Rate limited", response=mock_response),
            True # Success
        ]

        # We need to mock asyncio.sleep to avoid waiting
        with patch('asyncio.sleep', new_callable=AsyncMock):
            result = await slack_service.send_alert(
                title="Test Alert",
                message="Message"
            )

        assert result is True
        assert slack_service.client.chat_postMessage.call_count == 2

    @pytest.mark.asyncio
    async def test_deduplication(self, slack_service):
        """Test that duplicate alerts are suppressed."""
        slack_service.client = AsyncMock()
        
        # Send first alert
        await slack_service.send_alert(
            title="Duplicate",
            message="Msg",
            severity="info"
        )
        
        # Send duplicate
        result = await slack_service.send_alert(
            title="Duplicate",
            message="Msg",
            severity="info"
        )
        
        assert result is True
        # Should be called only once
        assert slack_service.client.chat_postMessage.call_count == 1

    @pytest.mark.asyncio
    async def test_send_digest(self, slack_service):
        """Test sending daily digest."""
        slack_service.client = AsyncMock()

        stats = {
            "total_cost": 100.0,
            "carbon_kg": 50.0,
            "zombie_count": 5
        }

        result = await slack_service.send_digest(stats)

        assert result is True
        slack_service.client.chat_postMessage.assert_called_once()
