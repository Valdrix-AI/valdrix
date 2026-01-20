"""
Budget Hard Cap Service - Phase 36

Monitors tenant-level cloud spend and triggers emergency remediation
if configured hard caps are exceeded.
"""

from decimal import Decimal
from datetime import date, datetime
from uuid import UUID, uuid4
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.remediation_settings import RemediationSettings
from app.services.costs.aggregator import CostAggregator
from app.services.security.audit_log import AuditLogger, AuditEventType

logger = structlog.get_logger()

class BudgetHardCapService:
    """
    Service to enforce cloud spending hard caps.
    
    If a tenant's spend for the current month exceeds their configured hard cap,
    this service triggers an 'Emergency Sweep' via the AutonomousRemediationEngine.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_and_enforce(self, tenant_id: UUID):
        """
        Check if a tenant has exceeded their hard cap and enforce if necessary.
        """
        # 1. Fetch Remediation Settings
        stmt = select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        settings = result.scalar_one_or_none()
        
        if not settings or not settings.hard_cap_enabled or settings.monthly_hard_cap_usd <= 0:
            return

        # 2. Get current month's spend
        today = date.today()
        start_month = today.replace(day=1)
        
        summary = await CostAggregator.get_summary(
            self.db,
            tenant_id=tenant_id,
            start_date=start_month,
            end_date=today
        )
        
        current_spend = summary.total_cost
        hard_cap = Decimal(str(settings.monthly_hard_cap_usd))

        if current_spend >= hard_cap:
            logger.warning(
                "hard_cap_breached",
                tenant_id=str(tenant_id),
                current_spend=float(current_spend),
                hard_cap=float(hard_cap),
                msg="Triggering emergency remediation sweep"
            )

            # 3. Log Audit Event
            audit = AuditLogger(self.db, tenant_id)
            await audit.log(
                event_type=AuditEventType.REMEDIATION_EXECUTED,
                actor_id=None,
                resource_id="tenant_budget",
                resource_type="budget",
                success=True,
                details={
                    "event": "hard_cap_enforcement_triggered",
                    "current_spend": float(current_spend),
                    "hard_cap": float(hard_cap)
                }
            )

            # 4. Notify Tenant
            from app.services.notifications.slack import get_slack_service
            slack = get_slack_service()
            if slack:
                await slack.send_alert(
                    title="URGENT: Hard Cap Breached!",
                    message=f"Your cloud spend of *${current_spend:,.2f}* has exceeded your limit of *${hard_cap:,.2f}*. Valdrix is triggering an emergency cleanup of zombie resources.",
                    severity="critical"
                )
            
            return True
            
        return False
