
import pytest
from unittest.mock import MagicMock, patch, ANY
from app.modules.notifications.domain.email_service import EmailService

@pytest.fixture
def email_service():
    return EmailService(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="password",
        from_email="noreply@valdrix.io"
    )

@pytest.mark.asyncio
async def test_send_carbon_alert_success(email_service):
    recipients = ["test@example.com"]
    status = {
        "alert_status": "exceeded",
        "current_usage_kg": 150,
        "budget_kg": 100,
        "usage_percent": 150,
        "recommendations": ["Reduce usage"]
    }
    
    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = mock_smtp.return_value.__enter__.return_value
        
        result = await email_service.send_carbon_alert(recipients, status)
        
        assert result is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "password")
        mock_server.sendmail.assert_called_once_with("noreply@valdrix.io", recipients, ANY)

@pytest.mark.asyncio
async def test_send_carbon_alert_no_recipients(email_service):
    result = await email_service.send_carbon_alert([], {})
    assert result is False

@pytest.mark.asyncio
async def test_send_carbon_alert_failure(email_service):
    with patch("smtplib.SMTP", side_effect=Exception("SMTP Error")):
        result = await email_service.send_carbon_alert(["test@example.com"], {})
        assert result is False

@pytest.mark.asyncio
async def test_send_dunning_notification_success(email_service):
    from datetime import datetime
    
    with patch("smtplib.SMTP") as mock_smtp:
        result = await email_service.send_dunning_notification(
            to_email="user@example.com",
            attempt=1,
            max_attempts=3,
            next_retry_date=datetime.now(),
            tier="Growth"
        )
        assert result is True

@pytest.mark.asyncio
async def test_send_payment_recovered(email_service):
    with patch("smtplib.SMTP") as mock_smtp:
        result = await email_service.send_payment_recovered_notification("user@example.com")
        assert result is True

@pytest.mark.asyncio
async def test_send_account_downgraded(email_service):
    with patch("smtplib.SMTP") as mock_smtp:
        result = await email_service.send_account_downgraded_notification("user@example.com")
        assert result is True
