from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation import RemediationAction, RemediationRequest, RemediationStatus
from app.modules.optimization.domain.remediation import RemediationService
from app.modules.optimization.domain.service import ZombieService
from app.shared.core.constants import SYSTEM_USER_ID
from app.shared.core.provider import normalize_provider

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

    @staticmethod
    def _coerce_provider(raw: Any) -> str:
        return normalize_provider(raw)

    @staticmethod
    def _coerce_uuid(raw: Any) -> UUID | None:
        if raw is None:
            return None
        try:
            return UUID(str(raw))
        except (TypeError, ValueError):
            return None

    async def _has_open_request(
        self,
        *,
        resource_id: str,
        provider: str,
        action: RemediationAction,
    ) -> bool:
        """
        Prevent duplicate autonomous requests for the same resource/action/provider.
        """
        open_statuses = (
            RemediationStatus.PENDING,
            RemediationStatus.PENDING_APPROVAL,
            RemediationStatus.APPROVED,
            RemediationStatus.SCHEDULED,
            RemediationStatus.EXECUTING,
        )
        result = await self.db.execute(
            select(RemediationRequest.id).where(
                RemediationRequest.tenant_id == self.tenant_id,
                RemediationRequest.resource_id == resource_id,
                RemediationRequest.provider == provider,
                RemediationRequest.action == action,
                RemediationRequest.status.in_(open_statuses),
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _resolve_action(
        provider: str, category: str, candidate: dict[str, Any]
    ) -> RemediationAction | None:
        provider_key = provider.strip().lower()
        category_key = category.strip().lower()
        action_hint = str(candidate.get("action") or "").strip().lower()
        resource_type = str(candidate.get("resource_type") or "").strip().lower()
        generic_manual_review_categories = {
            "unattached_volumes",
            "old_snapshots",
            "unused_elastic_ips",
            "orphan_load_balancers",
            "idle_rds_databases",
            "underused_nat_gateways",
            "idle_s3_buckets",
            "stale_ecr_images",
            "idle_sagemaker_endpoints",
            "cold_redshift_clusters",
            "idle_container_clusters",
            "unused_app_service_plans",
            "idle_serverless_services",
            "idle_serverless_functions",
            "orphan_network_components",
            "idle_platform_services",
            "idle_hybrid_resources",
        }

        provider_action_map: dict[str, dict[str, RemediationAction]] = {
            "aws": {
                "unattached_volumes": RemediationAction.DELETE_VOLUME,
                "old_snapshots": RemediationAction.DELETE_SNAPSHOT,
                "unused_elastic_ips": RemediationAction.RELEASE_ELASTIC_IP,
                "idle_instances": RemediationAction.STOP_INSTANCE,
                "orphan_load_balancers": RemediationAction.DELETE_LOAD_BALANCER,
                "idle_rds_databases": RemediationAction.STOP_RDS_INSTANCE,
                "underused_nat_gateways": RemediationAction.DELETE_NAT_GATEWAY,
                "idle_s3_buckets": RemediationAction.DELETE_S3_BUCKET,
                "stale_ecr_images": RemediationAction.DELETE_ECR_IMAGE,
                "idle_sagemaker_endpoints": RemediationAction.DELETE_SAGEMAKER_ENDPOINT,
                "cold_redshift_clusters": RemediationAction.DELETE_REDSHIFT_CLUSTER,
            },
            "azure": {
                "idle_instances": RemediationAction.DEALLOCATE_AZURE_VM,
            },
            "gcp": {
                "idle_instances": RemediationAction.STOP_GCP_INSTANCE,
            },
            "license": {
                "unused_license_seats": RemediationAction.RECLAIM_LICENSE_SEAT,
            },
            "platform": {
                "idle_platform_services": RemediationAction.MANUAL_REVIEW,
            },
            "hybrid": {
                "idle_hybrid_resources": RemediationAction.MANUAL_REVIEW,
            },
        }

        mapped_action = provider_action_map.get(provider_key, {}).get(category_key)
        if mapped_action is not None:
            return mapped_action

        if (
            provider_key in {"azure", "gcp", "saas", "license", "platform", "hybrid"}
            and category_key in generic_manual_review_categories
        ):
            return RemediationAction.MANUAL_REVIEW

        if provider_key == "saas":
            if action_hint == RemediationAction.REVOKE_GITHUB_SEAT.value:
                return RemediationAction.REVOKE_GITHUB_SEAT
            if "github" in resource_type and category_key == "unused_license_seats":
                return RemediationAction.REVOKE_GITHUB_SEAT
            if category_key in {"idle_saas_subscriptions", "unused_license_seats"}:
                return RemediationAction.MANUAL_REVIEW

        return None

    async def _process_candidate(
        self,
        service: RemediationService,
        resource_id: str,
        resource_type: str,
        provider: str,
        connection_id: UUID | None,
        action: Any,
        savings: float,
        confidence: float,
        reason: str,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        """Processes a single remediation candidate."""
        # BE-OP-Autonomous: High-Confidence Auto-Execution (Phase 8)
        if await self._has_open_request(
            resource_id=resource_id,
            provider=provider,
            action=action,
        ):
            logger.info(
                "autonomous_candidate_skipped_duplicate",
                tenant_id=str(self.tenant_id),
                provider=provider,
                resource_id=resource_id,
                action=action.value,
            )
            return False

        # 1. Create the request (Drafting)
        request = await service.create_request(
            tenant_id=self.tenant_id,
            user_id=SYSTEM_USER_ID,
            resource_id=resource_id,
            resource_type=resource_type,
            action=action,
            estimated_savings=savings,
            explainability_notes=f"Autonomous candidate: {reason} (Confidence: {confidence})",
            provider=provider,
            connection_id=connection_id,
            parameters=parameters,
        )

        # 2. Auto-Pilot Logic
        if self.auto_pilot_enabled and confidence >= 0.95:
            logger.info(
                "autonomous_auto_executing",
                tenant_id=str(self.tenant_id),
                resource_id=resource_id,
            )
            # System takes control
            await service.approve(
                request.id,
                self.tenant_id,
                reviewer_id=SYSTEM_USER_ID,
                notes="Auto-Pilot execution",
            )
            await service.execute(request.id, self.tenant_id)
            return True

        return False

    async def execute_automatic(self, recommendations: Iterable[dict[str, Any]]) -> int:
        """Automatically process remediation candidates and return auto-executed count."""
        recs = [rec for rec in recommendations if isinstance(rec, dict)]
        logger.info(
            "autonomous_execution_started",
            tenant_id=str(self.tenant_id),
            count=len(recs),
        )

        auto_executed = 0
        for rec in recs:
            provider = self._coerce_provider(rec.get("provider"))
            if not provider:
                logger.warning(
                    "autonomous_candidate_skipped_invalid_provider",
                    tenant_id=str(self.tenant_id),
                    provider=rec.get("provider"),
                    resource_id=rec.get("resource_id") or rec.get("id"),
                )
                continue
            action = self._resolve_action(provider, str(rec.get("category", "")), rec)
            resource_id = rec.get("resource_id") or rec.get("id")
            if not action or not resource_id:
                continue

            resource_type = str(
                rec.get("resource_type") or rec.get("type") or "unknown"
            )
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
            connection_id = self._coerce_uuid(rec.get("connection_id"))

            was_auto_executed = await self._process_candidate(
                service=self.service,
                resource_id=str(resource_id),
                resource_type=resource_type,
                provider=provider,
                connection_id=connection_id,
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
        connection_id: str | UUID | None = None,
    ) -> dict[str, Any]:
        """
        Scan tenant resources across providers and draft/execute remediation requests.

        Returns a stable summary contract used by governance job handlers.
        """
        del credentials
        mode = "autonomous" if self.auto_pilot_enabled else "dry_run"
        connection_filter = self._coerce_uuid(connection_id)
        try:
            scan_service = ZombieService(self.db)
            scan_results = await scan_service.scan_for_tenant(
                tenant_id=self.tenant_id,
                region=region or "global",
                analyze=False,
            )
            if not isinstance(scan_results, dict):
                raise ValueError("invalid scan payload")
            if scan_results.get("error"):
                return {
                    "mode": mode,
                    "scanned": 0,
                    "auto_executed": 0,
                    "error": "no_connections_found",
                }
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
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                provider = self._coerce_provider(item.get("provider"))
                if not provider:
                    continue
                action = self._resolve_action(provider, category, item)
                if action is None:
                    continue

                resource_id = item.get("resource_id") or item.get("id")
                if not resource_id:
                    continue

                candidate_connection_id = self._coerce_uuid(item.get("connection_id"))
                if connection_filter and candidate_connection_id != connection_filter:
                    continue

                candidates.append(
                    {
                        "provider": provider,
                        "resource_id": str(resource_id),
                        "resource_type": str(
                            item.get("resource_type") or item.get("type") or "unknown"
                        ),
                        "action": action,
                        "connection_id": candidate_connection_id,
                        "confidence": self._as_float(
                            item.get("confidence_score"), default=0.8
                        ),
                        "savings": self._as_float(
                            item.get("monthly_waste", item.get("monthly_cost")),
                            default=0.0,
                        ),
                        "reason": str(
                            item.get("explainability_notes")
                            or item.get("recommendation")
                            or f"Detected by autonomous sweep ({category})"
                        ),
                    }
                )

        auto_executed = 0
        for candidate in candidates:
            was_auto_executed = await self._process_candidate(
                service=self.service,
                resource_id=candidate["resource_id"],
                resource_type=candidate["resource_type"],
                provider=candidate["provider"],
                connection_id=candidate["connection_id"],
                action=candidate["action"],
                savings=candidate["savings"],
                confidence=candidate["confidence"],
                reason=candidate["reason"],
            )
            if was_auto_executed:
                auto_executed += 1

        return {
            "mode": mode,
            "scanned": len(candidates),
            "auto_executed": auto_executed,
        }

    @staticmethod
    def _as_float(raw: Any, default: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default
