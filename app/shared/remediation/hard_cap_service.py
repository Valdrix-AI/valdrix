from datetime import date
from decimal import Decimal
from uuid import UUID
from typing import Optional
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation_settings import RemediationSettings
from app.modules.reporting.domain.aggregator import CostAggregator
from app.modules.notifications.domain.slack import get_slack_service

logger = structlog.get_logger()

class BudgetHardCapService:
    """
    Service to enforce cloud budget hard-caps.
    If spend exceeds the configured threshold, it triggers notifications.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_and_enforce(self, tenant_id: UUID) -> Optional[bool]:
        """
        Check if the tenant has exceeded their monthly hard cap.
        Returns:
            True if cap is breached.
            False if within budget.
            None if no cap is configured.
        """
        # 1. Fetch settings
        result = await self.db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
        settings = result.scalar_one_or_none()
        
        if not settings or not settings.hard_cap_enabled:
            return None
            
        # 2. Calculate current month spend
        today = date.today()
        start_of_month = date(today.year, today.month, 1)
        
        summary = await CostAggregator.get_summary(
            self.db, 
            tenant_id, 
            start_date=start_of_month, 
            end_date=today
        )
        
        current_spend = summary.total_cost if hasattr(summary, "total_cost") else Decimal("0")
        cap = Decimal(str(settings.monthly_hard_cap_usd))
        
        # 3. Enforcement Logic
        if current_spend > cap:
            logger.warning("budget_hard_cap_breached", 
                          tenant_id=str(tenant_id), 
                          current_spend=float(current_spend), 
                          cap=float(cap))
            
            # Send Slack Alert
            slack = get_slack_service()
            if slack:
                percent_used = (float(current_spend) / float(cap) * 100.0) if cap > 0 else 100.0
                await slack.notify_budget_alert(
                    current_spend=float(current_spend),
                    budget_limit=float(cap),
                    percent_used=percent_used
                )
            
            return True
            
        return False
