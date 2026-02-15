"""
Tests for SlackService - Notification Coverage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.notifications.domain.slack import SlackService, get_slack_service


class TestSlackService:
    """Tests for SlackService."""

    def test_escape_mrkdwn_special_chars(self):
        """Test escaping Slack markdown special characters."""
        assert SlackService.escape_mrkdwn("<script>") == "&lt;script&gt;"
        assert SlackService.escape_mrkdwn("foo & bar") == "foo &amp; bar"
        assert SlackService.escape_mrkdwn("") == ""
        assert SlackService.escape_mrkdwn(None) == ""

    def test_init_sets_client_and_channel(self):
        """Test initialization sets up client and channel."""
        service = SlackService("xoxb-test-token", "#test-channel")
        assert service.channel_id == "#test-channel"
        assert service.client is not None

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """Test successful alert sending."""
        service = SlackService("xoxb-test", "#alerts")

        with patch.object(
            service.client, "chat_postMessage", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = {"ok": True}

            result = await service.send_alert(
                title="Test Alert", message="Test message", severity="warning"
            )

            assert result is True
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_deduplication(self):
        """Test that duplicate alerts are suppressed."""
        service = SlackService("xoxb-test", "#alerts")

        with patch.object(
            service.client, "chat_postMessage", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = {"ok": True}

            # First call
            await service.send_alert("Same Alert", "Same message", "info")
            # Second call with same title/severity/message - should be suppressed
            result = await service.send_alert("Same Alert", "Same message", "info")

            # Second should return True (suppressed) but only one actual call
            assert result is True
            assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_digest_success(self):
        """Test sending daily digest."""
        service = SlackService("xoxb-test", "#general")

        with patch.object(
            service.client, "chat_postMessage", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = {"ok": True}

            stats = {
                "total_cost": 123.45,
                "carbon_kg": 2.5,
                "zombie_count": 3,
                "period": "Last 24h",
            }

            result = await service.send_digest(stats)
            assert result is True

    @pytest.mark.asyncio
    async def test_notify_zombies_with_resources(self):
        """Test zombie notification with resources."""
        service = SlackService("xoxb-test", "#alerts")

        with patch.object(service, "send_alert", new_callable=AsyncMock) as mock_alert:
            mock_alert.return_value = True

            zombies = {
                "ebs_volumes": [{"id": "vol-1"}, {"id": "vol-2"}],
                "elastic_ips": [{"id": "eip-1"}],
            }

            result = await service.notify_zombies(zombies, estimated_savings=50.0)
            assert result is True
            mock_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_zombies_empty(self):
        """Test zombie notification with no resources."""
        service = SlackService("xoxb-test", "#alerts")

        result = await service.notify_zombies({}, estimated_savings=0)
        assert result is True  # Returns early without sending

    @pytest.mark.asyncio
    async def test_notify_budget_alert_warning(self):
        """Test budget alert with warning severity."""
        service = SlackService("xoxb-test", "#alerts")

        with patch.object(service, "send_alert", new_callable=AsyncMock) as mock_alert:
            mock_alert.return_value = True

            await service.notify_budget_alert(
                current_spend=80.0, budget_limit=100.0, percent_used=80.0
            )

            mock_alert.assert_called_once()
            # Should be warning (not critical) at 80%
            assert mock_alert.call_args.kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_notify_budget_alert_critical(self):
        """Test budget alert with critical severity when exceeded."""
        service = SlackService("xoxb-test", "#alerts")

        with patch.object(service, "send_alert", new_callable=AsyncMock) as mock_alert:
            mock_alert.return_value = True

            await service.notify_budget_alert(
                current_spend=110.0, budget_limit=100.0, percent_used=110.0
            )

            assert mock_alert.call_args.kwargs["severity"] == "critical"


class TestGetSlackService:
    """Tests for get_slack_service factory."""

    def test_returns_none_when_not_configured(self):
        """Test factory returns None when Slack is not configured."""
        with patch("app.shared.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                SLACK_BOT_TOKEN=None, SLACK_CHANNEL_ID=None
            )

            result = get_slack_service()
            assert result is None

    def test_returns_service_when_configured(self):
        """Test factory returns SlackService when configured."""
        with patch("app.shared.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                SLACK_BOT_TOKEN="xoxb-test-token",
                SLACK_CHANNEL_ID="#test-channel",
                SAAS_STRICT_INTEGRATIONS=False,
            )

            result = get_slack_service()
            assert isinstance(result, SlackService)

    def test_returns_none_when_strict_mode_enabled(self):
        """Test factory returns None when env integrations are disabled by strict SaaS mode."""
        with patch("app.shared.core.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                SLACK_BOT_TOKEN="xoxb-test-token",
                SLACK_CHANNEL_ID="#test-channel",
                SAAS_STRICT_INTEGRATIONS=True,
            )

            result = get_slack_service()
            assert result is None
