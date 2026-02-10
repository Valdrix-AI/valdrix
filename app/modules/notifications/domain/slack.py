"""
Slack notification service for Valdrix.
Sends alerts and daily digests to configured Slack channel.
"""
import structlog
from typing import Any
import asyncio
import hashlib
import time

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

logger = structlog.get_logger()


class SlackService:
    """Service for sending notifications to Slack."""

    # Color mapping for severity levels
    SEVERITY_COLORS = {
        "info": "#10b981",      # Green
        "warning": "#f59e0b",   # Amber
        "critical": "#f43f5e",  # Red
    }
    
    @staticmethod
    def escape_mrkdwn(text: str) -> str:
        """
        Escape Slack control characters to prevent mrkdwn injection.
        References: https://api.slack.com/reference/surfaces/formatting#escaping
        """
        if not text:
            return ""
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def __init__(self, bot_token: str, channel_id: str):
        """Initialize with bot token and target channel."""
        self.client = AsyncWebClient(token=bot_token)
        self.channel_id = channel_id
        
        # BE-NOTIF-4: Alert deduplication cache (stores alert hashes with timestamps)
        self._sent_alerts: dict[str, float] = {}
        self._dedup_window_seconds = 3600  # 1 hour deduplication window

    async def _send_with_retry(self, method: str, **kwargs) -> bool:
        """Generic Slack API call with exponential backoff for rate limiting."""
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                # Use getattr to call the method (e.g., chat_postMessage)
                func = getattr(self.client, method)
                await func(**kwargs)
                return True
            except SlackApiError as e:
                error_code = e.response.get('error', '')
                if error_code == 'ratelimited' and attempt < max_retries:
                    retry_after = int(e.response.headers.get('Retry-After', 2 ** attempt))
                    logger.warning("slack_rate_limited_retrying", retry_after=retry_after, attempt=attempt)
                    await asyncio.sleep(retry_after)
                    continue
                logger.error("slack_api_error", method=method, error_code=error_code)
                return False
            except Exception as e:
                logger.error("slack_method_failed", method=method, error=str(e))
                return False
        return False

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning"
    ) -> bool:
        """Send an alert message to Slack with retry logic and deduplication."""
        
        # BE-NOTIF-4: Check for duplicate alerts within dedup window
        # Include message hash to avoid suppressing distinct alerts with same title
        msg_hash = hashlib.sha256(message.encode()).hexdigest()[:12]
        alert_hash = hashlib.sha256(f"{title}:{severity}:{msg_hash}".encode()).hexdigest()
        current_time = time.time()

        
        if alert_hash in self._sent_alerts:
            last_sent = self._sent_alerts[alert_hash]
            if current_time - last_sent < self._dedup_window_seconds:
                logger.info("duplicate_alert_suppressed", title=title)
                return True  # Suppress duplicate
        
        # Record this alert
        self._sent_alerts[alert_hash] = current_time
        
        # Cleanup old entries (simple garbage collection)
        self._sent_alerts = {
            k: v for k, v in self._sent_alerts.items()
            if current_time - v < self._dedup_window_seconds
        }
        
        color = self.SEVERITY_COLORS.get(severity, self.SEVERITY_COLORS["warning"])
        return await self._send_with_retry(
            "chat_postMessage",
            channel=self.channel_id,
            text=f"Alert: {title}", # BE-NOTIF-5: Fallback text for notifications
            attachments=[
                {
                    "fallback": message, # BE-NOTIF-5: Legacy fallback for mobile
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

    async def send_digest(self, stats: dict[str, Any]) -> bool:
        """Send daily cost digest to Slack with retry logic."""
        return await self._send_with_retry(
            "chat_postMessage",
            channel=self.channel_id,
            text="Daily Cloud Cost Digest", # BE-NOTIF-5: Fallback text
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
                        {"type": "mrkdwn", "text": "Powered by Valdrix"}
                    ]
                }
            ]
        )

    async def notify_zombies(self, zombies: dict[str, Any], estimated_savings: float = 0.0) -> bool:
        """
        Send zombie detection alert.

        Args:
            zombies: Dict of zombie categories to lists of resources
            estimated_savings: Estimated monthly savings in dollars
        """
        zombie_count = sum(len(items) for items in zombies.values() if isinstance(items, list))
        if zombie_count == 0:
            return True  # No zombies, nothing to report

        summary_lines = []
        for cat, items in zombies.items():
            if isinstance(items, list) and len(items) > 0:
                # BE-SLACK-1: Escape category label
                safe_label = self.escape_mrkdwn(cat.replace("_", " ").title())
                summary_lines.append(f"• {safe_label}: {len(items)}")

        message = (
            f"Found *{zombie_count} zombie resources*.\n" +
            "\n".join(summary_lines) +
            f"\n💰 Estimated Savings: *${estimated_savings:.2f}/mo*"
        )

        return await self.send_alert(
            title="Zombie Resources Detected!",
            message=message,
            severity="warning"
        )

    async def notify_budget_alert(
        self,
        current_spend: float,
        budget_limit: float,
        percent_used: float
    ) -> bool:
        """
        Send budget threshold alert.

        Args:
            current_spend: Current spend amount
            budget_limit: Budget limit
            percent_used: Percentage of budget used (0-100)
        """
        severity = "critical" if percent_used >= 100 else "warning"

        message = (
            f"*Current Spend:* ${current_spend:.2f}\n"
            f"*Budget Limit:* ${budget_limit:.2f}\n"
            f"*Usage:* {percent_used:.1f}%"
        )

        return await self.send_alert(
            title="Budget Alert Threshold Reached",
            message=message,
            severity=severity
        )


def get_slack_service():
    """
    Factory function to get a configured SlackService instance.
    Returns None if Slack is not configured.
    """
    from app.shared.core.config import get_settings
    settings = get_settings()

    if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
        return SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)
    return None
