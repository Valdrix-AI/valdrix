
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from slack_sdk.errors import SlackApiError
from app.modules.notifications.domain.slack import SlackService

@pytest.fixture
def slack_service():
    return SlackService(bot_token="xoxb-test", channel_id="C123")

@pytest.mark.asyncio
async def test_send_alert_success(slack_service):
    slack_service.client.chat_postMessage = AsyncMock()
    
    result = await slack_service.send_alert("Test", "Message")
    assert result is True
    slack_service.client.chat_postMessage.assert_awaited_once()

@pytest.mark.asyncio
async def test_send_alert_deduplication(slack_service):
    slack_service.client.chat_postMessage = AsyncMock()
    
    # First send
    await slack_service.send_alert("Dupe", "Msg")
    
    # Second send (should be deduped)
    result = await slack_service.send_alert("Dupe", "Msg")
    
    assert result is True
    # Should still only be called once
    assert slack_service.client.chat_postMessage.call_count == 1

@pytest.mark.asyncio
async def test_send_with_retry_ratelimited(slack_service):
    # Mock response object that behaves like a SlackResponse (dict + attributes)
    class MockSlackResponse(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.headers = {"Retry-After": "1"}
            self.status_code = 429

    mock_response = MockSlackResponse({"ok": False, "error": "ratelimited"})
    
    error = SlackApiError(message="ratelimited", response=mock_response)
    
    slack_service.client.chat_postMessage = AsyncMock(side_effect=[error, True])
    
    with patch("asyncio.sleep", new_callable=AsyncMock): # Don't actually sleep
        result = await slack_service.send_alert("Test", "Msg")
        
        assert result is True
        assert slack_service.client.chat_postMessage.call_count == 2

@pytest.mark.asyncio
async def test_notify_zombies(slack_service):
    slack_service.send_alert = AsyncMock(return_value=True)
    
    zombies = {
        "ec2_instances": ["i-1"],
        "rds_clusters": []
    }
    
    await slack_service.notify_zombies(zombies, estimated_savings=10.0)
    
    slack_service.send_alert.assert_awaited_once()
    args = slack_service.send_alert.await_args[1]
    assert "Zombie Resources Detected" in args["title"]
    assert "Ec2 Instances: 1" in args["message"]
