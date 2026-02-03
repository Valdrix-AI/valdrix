"""
Notification Dispatcher - Unified Event-Driven Notifications

Bridges services (ZombieService, RemediationService) to actual providers (Slack, etc.).
This allows adding new channels (Teams, Discord, Email) without modifying domain logic.
"""

import structlog
from typing import Any, Dict
from app.modules.notifications.domain.slack import get_slack_service

logger = structlog.get_logger()

class NotificationDispatcher:
    """
    Dispatcher responsible for routing alerts to appropriate providers.
    Currently focuses on Slack as the primary channel.
    """
    
    @staticmethod
    async def send_alert(title: str, message: str, severity: str = "warning"):
        """Sends a generic alert to configured channels."""
        # Slack
        slack = get_slack_service()
        if slack:
            await slack.send_alert(title, message, severity)
        
        # In the future, loop through registered providers
        logger.info("notification_dispatched", title=title, severity=severity)

    @staticmethod
    async def notify_zombies(zombies: Dict[str, Any], estimated_savings: float = 0.0):
        """Dispatches zombie resource detection alerts."""
        slack = get_slack_service()
        if slack:
            await slack.notify_zombies(zombies, estimated_savings)

    @staticmethod
    async def notify_budget_alert(current_spend: float, budget_limit: float, percent_used: float):
        """Dispatches budget threshold alerts."""
        slack = get_slack_service()
        if slack:
            await slack.notify_budget_alert(current_spend, budget_limit, percent_used)

    @staticmethod
    async def notify_remediation_completed(tenant_id: str, resource_id: str, action: str, savings: float):
        """Dispatches remediation completion alerts."""
        title = f"Remediation Successful: {action.title()} {resource_id}"
        message = f"Tenant: {tenant_id}\nResource: {resource_id}\nAction: {action}\nMonthly Savings: ${savings:.2f}"
        
        await NotificationDispatcher.send_alert(title, message, severity="info")
