"""
Targeted tests for app/shared/core/notifications.py missing coverage
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.shared.core.notifications import NotificationDispatcher


class TestNotificationDispatcherCoverage:
    """Test notification dispatcher to achieve full coverage."""

    @pytest.mark.asyncio
    async def test_send_alert_with_slack(self):
        """Test send_alert with Slack service available."""
        mock_slack = AsyncMock()
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger') as mock_logger:
                await NotificationDispatcher.send_alert(
                    title="Test Alert",
                    message="Test message",
                    severity="warning"
                )
                
                mock_slack.send_alert.assert_called_once_with(
                    "Test Alert", "Test message", "warning"
                )
                mock_logger.info.assert_called_once_with(
                    "notification_dispatched",
                    title="Test Alert",
                    severity="warning"
                )

    @pytest.mark.asyncio
    async def test_send_alert_without_slack(self):
        """Test send_alert without Slack service."""
        with patch('app.shared.core.notifications.get_slack_service', return_value=None):
            with patch('app.shared.core.notifications.logger') as mock_logger:
                await NotificationDispatcher.send_alert(
                    title="Test Alert",
                    message="Test message",
                    severity="error"
                )
                
                # Should not raise exception, just log
                mock_logger.info.assert_called_once_with(
                    "notification_dispatched",
                    title="Test Alert",
                    severity="error"
                )

    @pytest.mark.asyncio
    async def test_send_alert_default_severity(self):
        """Test send_alert with default severity."""
        mock_slack = AsyncMock()
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger'):
                await NotificationDispatcher.send_alert(
                    title="Test Alert",
                    message="Test message"
                )
                
                mock_slack.send_alert.assert_called_once_with(
                    "Test Alert", "Test message", "warning"  # Default severity
                )

    @pytest.mark.asyncio
    async def test_notify_zombies_with_slack(self):
        """Test notify_zombies with Slack service available."""
        mock_slack = AsyncMock()
        zombies_data = {"ec2": [{"id": "i-123", "cost": 50.0}]}
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            await NotificationDispatcher.notify_zombies(zombies_data, estimated_savings=150.0)
            
            mock_slack.notify_zombies.assert_called_once_with(zombies_data, 150.0)

    @pytest.mark.asyncio
    async def test_notify_zombies_without_slack(self):
        """Test notify_zombies without Slack service."""
        zombies_data = {"ebs": [{"id": "vol-456", "cost": 25.0}]}
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=None):
            # Should not raise exception
            await NotificationDispatcher.notify_zombies(zombies_data, estimated_savings=75.0)

    @pytest.mark.asyncio
    async def test_notify_budget_alert_with_slack(self):
        """Test notify_budget_alert with Slack service available."""
        mock_slack = AsyncMock()
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            await NotificationDispatcher.notify_budget_alert(
                current_spend=850.0,
                budget_limit=1000.0,
                percent_used=85.0
            )
            
            mock_slack.notify_budget_alert.assert_called_once_with(850.0, 1000.0, 85.0)

    @pytest.mark.asyncio
    async def test_notify_budget_alert_without_slack(self):
        """Test notify_budget_alert without Slack service."""
        with patch('app.shared.core.notifications.get_slack_service', return_value=None):
            # Should not raise exception
            await NotificationDispatcher.notify_budget_alert(
                current_spend=1200.0,
                budget_limit=1000.0,
                percent_used=120.0
            )

    @pytest.mark.asyncio
    async def test_notify_remediation_completed(self):
        """Test notify_remediation_completed."""
        mock_slack = AsyncMock()
        
        with patch('app.shared.core.notifications.get_slack_service', return_value=mock_slack):
            with patch('app.shared.core.notifications.logger') as mock_logger:
                await NotificationDispatcher.notify_remediation_completed(
                    tenant_id="tenant-123",
                    resource_id="i-456789",
                    action="terminate",
                    savings=75.50
                )
                
                # Verify send_alert was called with correct parameters
                mock_slack.send_alert.assert_called_once()
                call_args = mock_slack.send_alert.call_args[0]
                
                assert call_args[0] == "Remediation Successful: Terminate i-456789"
                assert "Tenant: tenant-123" in call_args[1]
                assert "Resource: i-456789" in call_args[1]
                assert "Action: terminate" in call_args[1]
                assert "Monthly Savings: $75.50" in call_args[1]
                assert call_args[2] == "info"
                
                mock_logger.info.assert_called_once()
