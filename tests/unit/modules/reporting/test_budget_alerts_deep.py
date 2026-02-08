"""
Comprehensive tests for Budget Alerts module.
Tests budget alert triggering, notification workflows, and alert management.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta, date

import uuid

from app.modules.reporting.domain.budget_alerts import CarbonBudgetService


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    return AsyncMock()


@pytest.fixture
def tenant_id():
    """Create a test tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def alert_service(mock_db):
    """Create budget alert service."""
    return CarbonBudgetService(mock_db)


class TestCarbonBudgetService:
    """Test CarbonBudgetService methods."""

    @pytest.mark.asyncio
    async def test_get_budget_status_default(self, alert_service, mock_db, tenant_id):
        """Test status with no settings (defaults)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        status = await alert_service.get_budget_status(
            tenant_id=tenant_id,
            month_start=date(2023, 1, 1),
            current_co2_kg=50.0
        )

        assert status["budget_kg"] == 100.0
        assert status["usage_percent"] == 50.0
        assert status["alert_status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_budget_status_warning(self, alert_service, mock_db, tenant_id):
        """Test status at warning level."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.carbon_budget_kg = 100.0
        mock_settings.alert_threshold_percent = 80
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_db.execute.return_value = mock_result

        status = await alert_service.get_budget_status(
            tenant_id=tenant_id,
            month_start=date(2023, 1, 1),
            current_co2_kg=85.0
        )

        assert status["alert_status"] == "warning"
        assert len(status["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_get_budget_status_exceeded(self, alert_service, mock_db, tenant_id):
        """Test status when budget exceeded."""
        mock_settings = MagicMock()
        mock_settings.carbon_budget_kg = 100.0
        mock_settings.alert_threshold_percent = 80
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_db.execute.return_value = mock_result

        status = await alert_service.get_budget_status(
            tenant_id=tenant_id,
            month_start=date(2023, 1, 1),
            current_co2_kg=120.0
        )

        assert status["alert_status"] == "exceeded"

    @pytest.mark.asyncio
    async def test_should_send_alert_rate_limiting(self, alert_service, mock_db, tenant_id):
        """Test alert rate limiting."""
        # Case 1: No settings -> True
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        
        # Case 2: Settings exist, last alert today -> False
        mock_settings_today = MagicMock()
        mock_settings_today.last_alert_sent = datetime.now(timezone.utc)
        mock_result_today = MagicMock()
        mock_result_today.scalar_one_or_none.return_value = mock_settings_today

        # Case 3: Settings exist, last alert yesterday -> True
        mock_settings_yesterday = MagicMock()
        mock_settings_yesterday.last_alert_sent = datetime.now(timezone.utc) - timedelta(days=1)
        mock_result_yesterday = MagicMock()
        mock_result_yesterday.scalar_one_or_none.return_value = mock_settings_yesterday

        mock_db.execute.side_effect = [
            mock_result_none,
            mock_result_today,
            mock_result_yesterday
        ]

        # 1
        assert await alert_service.should_send_alert(tenant_id, "warning") is True
        # 2
        assert await alert_service.should_send_alert(tenant_id, "warning") is False
        # 3
        assert await alert_service.should_send_alert(tenant_id, "warning") is True

    @pytest.mark.asyncio
    async def test_send_carbon_alert_flow(self, alert_service, mock_db, tenant_id):
        """Test full alert flow."""
        budget_status = {
            "alert_status": "warning",
            "current_usage_kg": 85.0,
            "budget_kg": 100.0,
            "usage_percent": 85.0,
            "recommendations": ["Rec 1"]
        }

        # Mock dependencies
        with patch("app.shared.core.config.get_settings") as mock_get_settings, \
             patch("app.shared.core.logging.audit_log") as mock_audit, \
             patch("app.modules.notifications.domain.SlackService") as MockSlackService, \
             patch("app.modules.notifications.domain.email_service.EmailService") as MockEmailService:
            
            # Configure Slack mock
            mock_slack_instance = MockSlackService.return_value
            mock_slack_instance.send_alert = AsyncMock(return_value=True)

            # Configure Email mock
            mock_email_instance = MockEmailService.return_value
            mock_email_instance.send_carbon_alert = AsyncMock(return_value=True)

            mock_app_settings = MagicMock()
            mock_app_settings.SLACK_BOT_TOKEN = "token"
            mock_app_settings.SLACK_CHANNEL_ID = "channel"
            mock_app_settings.SMTP_HOST = "smtp"
            mock_get_settings.return_value = mock_app_settings

            # Mock DB responses for should_send_alert and notification settings
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None # No prev settings = send allowed
            # For notification settings query
            mock_notif_result = MagicMock()
            mock_notif_result.scalar_one_or_none.return_value = None # Default settings
            # For email settings query
            mock_carbon_result = MagicMock()
            mock_carbon_result.scalar_one_or_none.return_value = MagicMock(email_enabled=True, email_recipients="test@example.com")

            mock_db.execute.side_effect = [
                mock_result, # should_send_alert (CarbonSettings query)
                mock_notif_result, # NotificationSettings query
                mock_carbon_result, # CarbonSettings query (for email)
                MagicMock(), # mark_alert_sent
                MagicMock()  # commit
            ]

            sent = await alert_service.send_carbon_alert(tenant_id, budget_status)
            
            assert sent is True
            mock_audit.assert_called_once()
