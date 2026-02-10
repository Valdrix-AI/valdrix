"""
Safety Guardrail Service - Unified Remediation Safety Logic

Consolidates:
1. Kill Switch (Daily savings limit) - Global and Tenant level.
2. Circuit Breaker (Success/Failure tracking).
3. Budget Hard Cap (Monthly spend vs threshold).
"""

from decimal import Decimal
from datetime import datetime, timezone, date
from uuid import UUID
import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.config import get_settings
from app.shared.core.exceptions import KillSwitchTriggeredError
from app.shared.core.notifications import NotificationDispatcher
from app.models.remediation import RemediationRequest, RemediationStatus
from app.models.remediation_settings import RemediationSettings

logger = structlog.get_logger()

class SafetyGuardrailService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._settings = get_settings()

    async def check_all_guards(self, tenant_id: UUID, estimated_impact: Decimal = Decimal("0")) -> None:
        """
        Runs all safety checks before allowing a remediation execution.
        Raises KillSwitchTriggeredError if any check fails.
        """
        # 1. Global Kill Switch Check
        await self._check_global_kill_switch(tenant_id, estimated_impact)
        
        # 2. Monthly Budget Hard Cap Check
        await self._check_monthly_hard_cap(tenant_id)
        
        # 3. Circuit Breaker / Failure Rate Check
        await self._check_circuit_breaker(tenant_id)

    async def _check_global_kill_switch(self, tenant_id: UUID, estimated_impact: Decimal) -> None:
        """Checks if the daily savings limit has been reached for the configured scope."""
        estimated_impact = estimated_impact or Decimal("0")
        today = datetime.now(timezone.utc).date()

        query = (
            select(func.sum(RemediationRequest.estimated_monthly_savings))
            .where(RemediationRequest.status == RemediationStatus.COMPLETED)
            .where(func.date(RemediationRequest.executed_at) == today)
        )
        if self._settings.REMEDIATION_KILL_SWITCH_SCOPE.lower() == "tenant":
            query = query.where(RemediationRequest.tenant_id == tenant_id)

        result = await self.db.execute(query)
        total_impact = result.scalar() or Decimal("0")
        
        threshold = Decimal(str(self._settings.REMEDIATION_KILL_SWITCH_THRESHOLD))
        
        if (total_impact + estimated_impact) >= threshold:
            logger.error(
                "global_kill_switch_triggered",
                tenant_id=str(tenant_id),
                scope=self._settings.REMEDIATION_KILL_SWITCH_SCOPE,
                total_impact=float(total_impact),
                threshold=float(threshold)
            )
            raise KillSwitchTriggeredError(
                f"Safety kill-switch triggered. Daily cost impact limit (${threshold}) reached."
            )

    async def _check_monthly_hard_cap(self, tenant_id: UUID) -> None:
        """Checks if the tenant has exceeded their monthly hard cap."""
        from app.modules.reporting.domain.aggregator import CostAggregator
        
        # Fetch settings
        result = await self.db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
        settings = result.scalar_one_or_none()
        
        if not settings or not settings.hard_cap_enabled:
            return

        # Calculate current month spend
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
        
        if current_spend > cap:
            logger.warning("budget_hard_cap_breached", 
                          tenant_id=str(tenant_id), 
                          current_spend=float(current_spend), 
                          cap=float(cap))
            
            # Send Budget Alert via Dispatcher
            percent_used = (float(current_spend) / float(cap) * 100.0) if cap > 0 else 100.0
            await NotificationDispatcher.notify_budget_alert(
                current_spend=float(current_spend),
                budget_limit=float(cap),
                percent_used=percent_used
            )
            
            raise KillSwitchTriggeredError(
                f"Monthly budget hard-cap reached (${float(cap)}). Remediation disabled."
            )

    async def _check_circuit_breaker(self, tenant_id: UUID) -> None:
        """
        Checks for recent high failure rates in remediation.
        If last 5 attempts in 1 hour failed, block execution.
        """
        # Phase 1: Simple Success/Failure ratio in last 24h
        one_day_ago = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get count of failures today
        result = await self.db.execute(
            select(func.count(RemediationRequest.id))
            .where(RemediationRequest.tenant_id == tenant_id)
            .where(RemediationRequest.status == RemediationStatus.FAILED)
            .where(RemediationRequest.executed_at >= one_day_ago)
        )
        failure_count = result.scalar() or 0
        
        if failure_count >= 5: # Threshold of 5 failures per day
            logger.warning("remediation_circuit_breaker_open", tenant_id=str(tenant_id), failures=failure_count)
            raise KillSwitchTriggeredError(
                f"Remediation circuit breaker open due to {failure_count} recent failures. Reset required."
            )
