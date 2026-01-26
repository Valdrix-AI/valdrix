"""
Tests for SlackService notification functionality.

Tests cover:
- Sending alerts with different severity levels
- Sending daily digest summaries
- Error handling when Slack API fails
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.notifications.domain.slack import SlackService


class TestSlackService:
    """Test suite for SlackService."""
    
    @pytest.fixture
    def mock_web_client(self):
        """Create a mock Slack WebClient."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock:
            yield mock
    
    @pytest.fixture
    def slack_service(self, mock_web_client):
        """Create SlackService with mocked client."""
        service = SlackService(
            bot_token="xoxb-test-token",
            channel_id="C12345678"
        )
        return service


class TestSendAlert:
    """Tests for send_alert method."""
    
    @pytest.mark.asyncio
    async def test_send_alert_info_severity(self):
        """Test sending an info-level alert."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(return_value={"ok": True})
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_alert(
                title="Test Alert",
                message="This is a test",
                severity="info"
            )
            
            assert result is True
            mock_instance.chat_postMessage.assert_called_once()
            call_args = mock_instance.chat_postMessage.call_args
            assert call_args.kwargs["channel"] == "C123"
            # Check that color is green for info
            assert call_args.kwargs["attachments"][0]["color"] == "#10b981"
    
    @pytest.mark.asyncio
    async def test_send_alert_warning_severity(self):
        """Test sending a warning-level alert."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(return_value={"ok": True})
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_alert(
                title="Warning Alert",
                message="Budget threshold reached",
                severity="warning"
            )
            
            assert result is True
            call_args = mock_instance.chat_postMessage.call_args
            # Check that color is amber for warning
            assert call_args.kwargs["attachments"][0]["color"] == "#f59e0b"
    
    @pytest.mark.asyncio
    async def test_send_alert_critical_severity(self):
        """Test sending a critical-level alert."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(return_value={"ok": True})
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_alert(
                title="Critical Alert",
                message="Budget exceeded!",
                severity="critical"
            )
            
            assert result is True
            call_args = mock_instance.chat_postMessage.call_args
            # Check that color is red for critical
            assert call_args.kwargs["attachments"][0]["color"] == "#f43f5e"
    
    @pytest.mark.asyncio
    async def test_send_alert_api_failure(self):
        """Test handling of Slack API failures."""
        from slack_sdk.errors import SlackApiError
        
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(side_effect=SlackApiError(
                message="channel_not_found",
                response={"error": "channel_not_found"}
            ))
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_alert(
                title="Test",
                message="Test",
                severity="info"
            )
            
            # Should return False, not raise exception
            assert result is False


class TestSendDigest:
    """Tests for send_digest method."""
    
    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        """Test sending daily digest with all stats."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(return_value={"ok": True})
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_digest({
                "total_cost": 125.50,
                "carbon_kg": 2.5,
                "zombie_count": 3,
                "period": "2026-01-08 - 2026-01-09"
            })
            
            assert result is True
            mock_instance.chat_postMessage.assert_called_once()
            call_args = mock_instance.chat_postMessage.call_args
            
            # Verify blocks contain expected data
            blocks = call_args.kwargs["blocks"]
            assert any("Daily Cloud Cost Digest" in str(block) for block in blocks)
    
    @pytest.mark.asyncio
    async def test_send_digest_handles_missing_stats(self):
        """Test digest handles missing stats gracefully."""
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(return_value={"ok": True})
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_digest({})  # Empty stats
            
            assert result is True  # Should still succeed with defaults
    
    @pytest.mark.asyncio
    async def test_send_digest_api_failure(self):
        """Test digest handles API failure gracefully."""
        from slack_sdk.errors import SlackApiError
        
        with patch("app.modules.notifications.domain.slack.AsyncWebClient") as mock_client:
            mock_instance = MagicMock()
            mock_instance.chat_postMessage = AsyncMock(side_effect=SlackApiError(
                message="invalid_auth",
                response={"error": "invalid_auth"}
            ))
            mock_client.return_value = mock_instance
            
            service = SlackService("xoxb-test", "C123")
            result = await service.send_digest({"total_cost": 100})
            
            assert result is False
