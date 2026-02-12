from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation import RemediationAction
from app.modules.optimization.adapters.aws.detector import AWSZombieDetector
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.core.constants import SYSTEM_USER_ID

logger = structlog.get_logger()

class AutonomousRemediationEngine:
    """
    Engine for autonomous remediation (ActiveOps).
    Bridges to RemediationService for execution.
    """
    def __init__(self, db: AsyncSession, tenant_id: str | UUID):
        self.db = db
        self.tenant_id = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        self.service = RemediationService(db)
        self.auto_pilot_enabled = False  # Default to Dry Run

    async def _process_candidate(
        self, 
        service: RemediationService,
        resource_id: str,
        resource_type: str,
        action: Any,
        savings: float,
        confidence: float,
        reason: str
    ) -> bool:
        """Processes a single remediation candidate."""
        # BE-OP-Autonomous: High-Confidence Auto-Execution (Phase 8)
        
        # 1. Create the request (Drafting)
        request = await service.create_request(
            tenant_id=self.tenant_id,
            user_id=SYSTEM_USER_ID,
            resource_id=resource_id,
            resource_type=resource_type,
            action=action,
            estimated_savings=savings,
            explainability_notes=f"Autonomous candidate: {reason} (Confidence: {confidence})"
        )
        
        # 2. Auto-Pilot Logic
        if self.auto_pilot_enabled and confidence >= 0.95:
            logger.info("autonomous_auto_executing", tenant_id=str(self.tenant_id), resource_id=resource_id)
            # System takes control
            await service.approve(request.id, self.tenant_id, reviewer_id=SYSTEM_USER_ID, notes="Auto-Pilot execution")
            await service.execute(request.id, self.tenant_id)
            return True
            
        return False

    async def execute_automatic(self, recommendations: Iterable[dict[str, Any]]) -> int:
        """Automatically process remediation candidates and return auto-executed count."""
        recs = [rec for rec in recommendations if isinstance(rec, dict)]
        logger.info("autonomous_execution_started", tenant_id=str(self.tenant_id), count=len(recs))

        auto_executed = 0
        for rec in recs:
            action = self._map_category_to_action(str(rec.get("category", "")))
            resource_id = rec.get("resource_id") or rec.get("id")
            if not action or not resource_id:
                continue

            resource_type = str(rec.get("resource_type") or rec.get("type") or "unknown")
            confidence = self._as_float(rec.get("confidence_score"), default=0.8)
            savings = self._as_float(
                rec.get("monthly_waste", rec.get("monthly_cost")),
                default=0.0,
            )
            reason = str(
                rec.get("explainability_notes")
                or rec.get("recommendation")
                or f"Detected by autonomous sweep ({rec.get('category', 'unknown')})"
            )

            was_auto_executed = await self._process_candidate(
                service=self.service,
                resource_id=str(resource_id),
                resource_type=resource_type,
                action=action,
                savings=savings,
                confidence=confidence,
                reason=reason,
            )
            if was_auto_executed:
                auto_executed += 1

        logger.info(
            "autonomous_execution_finished",
            tenant_id=str(self.tenant_id),
            candidates=len(recs),
            auto_executed=auto_executed,
        )
        return auto_executed

    async def run_autonomous_sweep(
        self,
        *,
        region: str,
        credentials: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Scan AWS resources and draft/execute remediation requests from candidates.

        Returns a stable summary contract used by governance job handlers.
        """
        mode = "autonomous" if self.auto_pilot_enabled else "dry_run"
        try:
            detector = AWSZombieDetector(
                region=region or "us-east-1",
                credentials=credentials or {},
                db=self.db,
            )
            scan_results = await detector.scan_all()
        except Exception as exc:
            logger.error(
                "autonomous_sweep_scan_failed",
                tenant_id=str(self.tenant_id),
                region=region,
                error=str(exc),
            )
            return {
                "mode": mode,
                "scanned": 0,
                "auto_executed": 0,
                "error": "scan_failed",
            }

        candidates: list[dict[str, Any]] = []
        for category, items in scan_results.items():
            action = self._map_category_to_action(category)
            if action is None or not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                with_category = dict(item)
                with_category["category"] = category
                candidates.append(with_category)

        auto_executed = await self.execute_automatic(candidates)
        return {
            "mode": mode,
            "scanned": len(candidates),
            "auto_executed": auto_executed,
        }

    @staticmethod
    def _map_category_to_action(category: str) -> RemediationAction | None:
        mapping = {
            "unattached_volumes": RemediationAction.DELETE_VOLUME,
            "old_snapshots": RemediationAction.DELETE_SNAPSHOT,
            "unused_elastic_ips": RemediationAction.RELEASE_ELASTIC_IP,
            "idle_instances": RemediationAction.STOP_INSTANCE,
            "orphan_load_balancers": RemediationAction.DELETE_LOAD_BALANCER,
            "idle_rds_databases": RemediationAction.STOP_RDS_INSTANCE,
            "underused_nat_gateways": RemediationAction.DELETE_NAT_GATEWAY,
            "stale_ecr_images": RemediationAction.DELETE_ECR_IMAGE,
            "idle_sagemaker_endpoints": RemediationAction.DELETE_SAGEMAKER_ENDPOINT,
            "cold_redshift_clusters": RemediationAction.DELETE_REDSHIFT_CLUSTER,
        }
        return mapping.get(category)

    @staticmethod
    def _as_float(raw: Any, default: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
