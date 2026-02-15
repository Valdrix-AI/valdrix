import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.notifications.domain.slack import SlackService
from app.modules.notifications.domain.email_service import EmailService


# --- Slack Service Tests ---
@pytest.mark.asyncio
async def test_slack_alert_deduplication():
    """Test that duplicate alerts within window are suppressed."""
    service = SlackService("token", "channel")
    service._send_with_retry = AsyncMock(return_value=True)

    # Send first
    await service.send_alert("Test Alert", "msg", severity="warning")
    service._send_with_retry.assert_called_once()
    service._send_with_retry.reset_mock()

    # Send duplicate immediately
    await service.send_alert("Test Alert", "msg", severity="warning")
    service._send_with_retry.assert_not_called()  # Should be deduplicated

    # Send different
    await service.send_alert("New Alert", "msg", severity="warning")
    service._send_with_retry.assert_called_once()


@pytest.mark.asyncio
async def test_slack_rate_limit_retry():
    """Test retry logic on rate limit."""
    service = SlackService("token", "channel")

    # Mock slack_sdk.errors.SlackApiError (needs response attribute)
    from slack_sdk.errors import SlackApiError

    rate_limit_err = SlackApiError("ratelimited", {"error": "ratelimited"})
    # Mock response object structure
    rate_limit_err.response = MagicMock()
    rate_limit_err.response.get.side_effect = (
        lambda k, d=None: "ratelimited" if k == "error" else d
    )
    rate_limit_err.response.headers = {"Retry-After": "1"}

    service.client.chat_postMessage = AsyncMock(side_effect=[rate_limit_err, True])

    with patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        success = await service.send_alert("Title", "Msg")
        assert success is True
        assert service.client.chat_postMessage.call_count == 2
        mock_sleep.assert_awaited_with(1)


# --- Email Service Tests ---
@pytest.mark.asyncio
async def test_email_carbon_alert():
    """Test email sending flow."""
    service = EmailService(
        "smtp.example.com", 587, "user", "pass", "no-reply@example.com"
    )

    with patch("smtplib.SMTP") as MockSMTP:
        smtp_instance = MockSMTP.return_value.__enter__.return_value

        success = await service.send_carbon_alert(
            recipients=["user@example.com"],
            budget_status={"alert_status": "exceeded", "current_usage_kg": 150},
        )

        assert success is True
        smtp_instance.starttls.assert_called()
        smtp_instance.login.assert_called()
        smtp_instance.sendmail.assert_called()
