"""
License Governance Service - Autonomous SaaS/License Reclamation Loop.

Implements "Phase 8: Autonomous License Lifecycle" with a notify-before-revoke workflow.
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID
from typing import Dict, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.shared.core.service import BaseService
from app.models.license_connection import LicenseConnection
from app.models.remediation_settings import RemediationSettings
from app.models.remediation import RemediationAction
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.adapters.license import LicenseAdapter
from app.shared.core.credentials import LicenseCredentials
from app.shared.core.constants import SYSTEM_USER_ID

logger = structlog.get_logger()


class LicenseGovernanceService(BaseService):
    """
    Orchestrates autonomous license governance:
    1. Scan connections for inactive users.
    2. Create remediation requests (pending or scheduled).
    3. Generate optimization insights.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.remediation_service = RemediationService(db)

    async def get_governance_settings(self, tenant_id: UUID) -> RemediationSettings | None:
        result = await self.db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def run_tenant_governance(self, tenant_id: UUID) -> Dict[str, Any]:
        """
        Runs the governance loop for a specific tenant.
        """
        settings = await self.get_governance_settings(tenant_id)
        if not settings or not settings.license_auto_reclaim_enabled:
            logger.info("license_governance_skipped_disabled", tenant_id=str(tenant_id))
            return {"status": "skipped", "reason": "feature_disabled"}

        # 1. Fetch all license connections for the tenant
        result = await self.db.execute(
            select(LicenseConnection).where(LicenseConnection.tenant_id == tenant_id)
        )
        connections = result.scalars().all()
        
        stats = {"connections_scanned": 0, "users_flagged": 0, "requests_created": 0}
        
        for conn in connections:
            try:
                stats["connections_scanned"] += 1
                creds = LicenseCredentials(
                    vendor=conn.vendor,
                    auth_method=conn.auth_method,
                    api_key=conn.api_key,
                    connector_config=conn.connector_config or {}
                )
                adapter = LicenseAdapter(creds)
                
                # Fetch users activity
                users = await adapter.list_users_activity()
                if not users:
                    continue

                threshold_days = settings.license_inactive_threshold_days
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)

                for user in users:
                    last_active = user.get("last_active_at")
                    
                    # Safety check: skip admins and non-inactive users
                    if user.get("is_admin") or not last_active:
                        continue
                        
                    if last_active < cutoff_date:
                        stats["users_flagged"] += 1
                        
                        # Create remediation request
                        request = await self.remediation_service.create_request(
                            tenant_id=tenant_id,
                            user_id=SYSTEM_USER_ID,
                            resource_id=user["user_id"],
                            resource_type="license_seat",
                            action=RemediationAction.RECLAIM_LICENSE_SEAT,
                            estimated_savings=creds.connector_config.get("default_seat_price_usd", 12.0),
                            provider="license",
                            connection_id=conn.id,
                            confidence_score=1.0,
                            explainability_notes=f"User {user['email']} inactive since {last_active.isoformat()}.",
                            parameters={"email": user["email"], "last_active_at": last_active.isoformat()}
                        )
                        stats["requests_created"] += 1
                        
                        # If auto-pilot is enabled for this tenant, trigger execution (which handles grace period)
                        if settings.auto_pilot_enabled:
                            # Note: execute() handles the SCHEDULED status and grace period logic
                            await self.remediation_service.execute(request.id, tenant_id)
                            
                            # NOW: Notify!
                            from app.shared.core.notifications import NotificationDispatcher
                            await NotificationDispatcher.notify_license_reclamation(
                                tenant_id=str(tenant_id),
                                user_email=user["email"],
                                last_active_at=last_active,
                                savings=float(creds.connector_config.get("default_seat_price_usd", 12.0)),
                                grace_period_days=settings.license_reclaim_grace_period_days,
                                request_id=str(request.id),
                                db=self.db
                            )

            except Exception as e:
                logger.error("license_governance_connection_failed", tenant_id=str(tenant_id), connection_id=str(conn.id), error=str(e))
                continue

        logger.info("license_governance_completed", tenant_id=str(tenant_id), stats=stats)
        return {"status": "completed", "stats": stats}
