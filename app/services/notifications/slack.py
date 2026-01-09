"""
Slack notification service for CloudSentinel.
Sends alerts and daily digests to configured Slack channel.
"""
import logging
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


class SlackService:
    """Service for sending notifications to Slack."""
    
    # Color mapping for severity levels
    SEVERITY_COLORS = {
        "info": "#10b981",      # Green
        "warning": "#f59e0b",   # Amber  
        "critical": "#f43f5e",  # Red
    }
    
    def __init__(self, bot_token: str, channel_id: str):
        """Initialize with bot token and target channel."""
        self.client = WebClient(token=bot_token)
        self.channel_id = channel_id
        
    async def send_alert(
        self, 
        title: str, 
        message: str, 
        severity: str = "warning"
    ) -> bool:
        """
        Send an alert message to Slack.
        
        Args:
            title: Alert headline
            message: Detailed message
            severity: info | warning | critical
            
        Returns:
            True if sent successfully, False otherwise
        """
        color = self.SEVERITY_COLORS.get(severity, self.SEVERITY_COLORS["warning"])
        
        try:
            # WebClient is sync, so we use it directly (it's fast enough)
            self.client.chat_postMessage(
                channel=self.channel_id,
                attachments=[
                    {
                        "color": color,
                        "blocks": [
                            {
                                "type": "header",
                                "text": {"type": "plain_text", "text": f"🚨 {title}"}
                            },
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": message}
                            },
                        ]
                    }
                ]
            )
            logger.info(f"Slack alert sent: {title}")
            return True
        except SlackApiError as e:
            logger.error(f"Slack API error: {e.response['error']}")
            return False
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False
            
    async def send_digest(self, stats: dict[str, Any]) -> bool:
        """
        Send daily cost digest to Slack.
        
        Args:
            stats: Dict with keys: total_cost, carbon_kg, zombie_count, period
        """
        try:
            self.client.chat_postMessage(
                channel=self.channel_id,
                blocks=[
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "📊 Daily Cloud Cost Digest"}
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*💰 Total Cost*\n${stats.get('total_cost', 0):.2f}"},
                            {"type": "mrkdwn", "text": f"*🌱 Carbon*\n{stats.get('carbon_kg', 0):.2f} kg CO₂"},
                            {"type": "mrkdwn", "text": f"*👻 Zombies*\n{stats.get('zombie_count', 0)} resources"},
                            {"type": "mrkdwn", "text": f"*📅 Period*\n{stats.get('period', 'Last 24h')}"},
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {"type": "mrkdwn", "text": "Powered by CloudSentinel AI"}
                        ]
                    }
                ]
            )
            logger.info("Slack daily digest sent")
            return True
        except SlackApiError as e:
            logger.error(f"Slack digest error: {e.response['error']}")
            return False