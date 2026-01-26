"""
Tests for EmailService - SMTP Notifications
"""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone
from app.modules.notifications.domain.email_service import EmailService


@pytest.fixture
def email_service():
    return EmailService(
        smtp_host="localhost",
        smtp_port=1025,
        smtp_user="user",
        smtp_password="password",
        from_email="noreply@v.io"
    )


def test_escape_html():
    from app.modules.notifications.domain.email_service import escape_html
    assert escape_html("<script>") == "&lt;script&gt;"


@pytest.mark.asyncio
async def test_send_carbon_alert_success(email_service):
    """Test sending carbon alert email."""
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = mock_smtp_cls.return_value.__enter__.return_value
        
        budget_status = {
            "tier": "growth",
            "current_usage": 1500,
            "budget_limit": 1000,
            "utilization": 150.0,
            "is_exceeded": True
        }
        
        res = await email_service.send_carbon_alert(["to@v.io"], budget_status)
        
        assert res is True
        mock_smtp.sendmail.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "password")


@pytest.mark.asyncio
async def test_send_carbon_alert_failure(email_service):
    """Test graceful failure on SMTP error."""
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = mock_smtp_cls.return_value.__enter__.return_value
        mock_smtp.sendmail.side_effect = Exception("smtp fail")
        
        res = await email_service.send_carbon_alert(["to@v.io"], {"tier": "starter"})
        assert res is False


@pytest.mark.asyncio
async def test_send_dunning_notification(email_service):
    """Test dunning notification email."""
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp = mock_smtp_cls.return_value.__enter__.return_value
        
        res = await email_service.send_dunning_notification(
            "to@v.io", 1, 3, datetime.now(timezone.utc), "growth"
        )
        assert res is True
        mock_smtp.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_send_payment_recovered(email_service):
    """Test payment recovered notification email."""
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value
        res = await email_service.send_payment_recovered_notification("to@v.io")
        assert res is True


@pytest.mark.asyncio
async def test_send_account_downgraded(email_service):
    """Test account downgraded notification email."""
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__.return_value
        res = await email_service.send_account_downgraded_notification("to@v.io")
        assert res is True
