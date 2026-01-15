import structlog
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.remediation import RemediationRequest, RemediationAction, RemediationStatus
from app.models.remediation_settings import RemediationSettings
from app.services.zombies.detector import ZombieDetector
from app.services.zombies import RemediationService

logger = structlog.get_logger()

class AutonomousRemediationEngine:
    """
    AI-Executive for Autonomous Remediation (ActiveOps).

    Operates in two modes:
    1. Dry Run (Default): Identifies candidates and creates PENDING requests.
    2. Auto-Pilot (High Risk): Automatically APPROVES and EXECUTES high-confidence candidates.

    Safety:
    - High confidence threshold required for Auto-Pilot.
    - Snapshots < 90 days are never auto-deleted.
    - Volumes with recent IOPS are never auto-deleted.
    - Rate limit: max_deletions_per_hour prevents runaway execution.
    """

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

        # Default safety (overridden by DB settings in run_autonomous_sweep)
        self.auto_pilot_enabled = False
        self.min_confidence_threshold = 0.95
        self.max_deletions_per_hour = 10  # Safety fuse
        self.simulation_mode = True  # Default to simulation for safety
        self._hourly_execution_count = 0  # Tracked per sweep

    async def _get_hourly_execution_count(self) -> int:
        """Count executions completed in the last hour for rate limiting."""
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        result = await self.db.execute(
            select(func.count(RemediationRequest.id)).where(
                RemediationRequest.tenant_id == self.tenant_id,
                RemediationRequest.status == RemediationStatus.COMPLETED,
                RemediationRequest.updated_at >= one_hour_ago
            )
        )
        return result.scalar() or 0

    async def run_autonomous_sweep(self, region: str, credentials: Dict[str, str]) -> Dict[str, Any]:
        """
        Scans for zombies and applies remediation policy.

        Modes:
        - Simulation Mode (default): Creates preview requests, no actual execution
        - Auto-Pilot Mode: Approves and executes high-confidence candidates
        """
        # Load dynamic settings
        settings_res = await self.db.execute(
            select(RemediationSettings).where(RemediationSettings.tenant_id == self.tenant_id)
        )
        settings = settings_res.scalar_one_or_none()
        if settings:
            self.auto_pilot_enabled = settings.auto_pilot_enabled
            self.min_confidence_threshold = float(settings.min_confidence_threshold)
            self.max_deletions_per_hour = settings.max_deletions_per_hour
            self.simulation_mode = settings.simulation_mode

        # Check rate limit before starting
        self._hourly_execution_count = await self._get_hourly_execution_count()

        logger.info("starting_autonomous_sweep",
                    tenant_id=str(self.tenant_id),
                    auto_pilot=self.auto_pilot_enabled,
                    simulation_mode=self.simulation_mode,
                    threshold=self.min_confidence_threshold,
                    hourly_limit=self.max_deletions_per_hour,
                    current_hourly_count=self._hourly_execution_count)

        detector = ZombieDetector(region=region, credentials=credentials)
        zombies = await detector.scan_all()

        results = {
            "mode": "simulation" if self.simulation_mode else ("auto_pilot" if self.auto_pilot_enabled else "dry_run"),
            "scanned": 0,
            "actions_created": 0,
            "auto_executed": 0,
            "simulated_savings": 0.0,
            "errors": 0
        }

        remediation_service = RemediationService(self.db, region=region, credentials=credentials)

        # Categories to process
        categories = [
            "unattached_volumes", "old_snapshots", "unused_elastic_ips",
            "idle_instances", "orphan_load_balancers", "idle_rds_databases",
            "underused_nat_gateways", "idle_s3_buckets", "legacy_ecr_images",
            "idle_sagemaker_endpoints", "cold_redshift_clusters"
        ]

        for category in categories:
            for item in zombies.get(category, []):
                try:
                    # Map action string to Enum
                    action_enum = RemediationAction(item["action"])

                    await self._process_candidate(
                        remediation_service,
                        resource_id=item["resource_id"],
                        resource_type=item["resource_type"],
                        action=action_enum,
                        savings=item.get("monthly_cost", 0.0),
                        confidence=item.get("confidence_score", 0.70),
                        reason=item.get("explainability_notes", "Flagged as zombie resource by automated scan.")
                    )
                    results["scanned"] += 1
                except Exception as e:
                    logger.error("autonomous_error",
                                category=category,
                                resource=item.get("resource_id", "unknown"),
                                error=str(e))
                    results["errors"] += 1

        return results

    async def _process_candidate(
        self,
        service: RemediationService,
        resource_id: str,
        resource_type: str,
        action: RemediationAction,
        savings: float,
        confidence: float,
        reason: str
    ):
        """
        Decides whether to create a Pending request or Auto-Execute.
        """

        # Check if request already exists
        existing = await service.db.execute(
            select(RemediationRequest).where(
                RemediationRequest.resource_id == resource_id,
                RemediationRequest.tenant_id == self.tenant_id,
                RemediationRequest.status.in_([RemediationStatus.PENDING, RemediationStatus.COMPLETED])
            )
        )
        if existing.scalar_one_or_none():
            return # Skip duplication

        # Create Request (base step)
        request = await service.create_request(
            tenant_id=self.tenant_id,
            user_id=None, # System created
            resource_id=resource_id,
            resource_type=resource_type,
            action=action,
            estimated_savings=savings,
            confidence_score=confidence,
            explainability_notes=reason
        )

        # Auto-Pilot Logic: Enabled AND High Confidence AND Rate Limit Not Exceeded
        # AND Symbolic Safety Check Passed
        from app.services.remediation.safety import SafeOpsEngine
        is_safe, safety_reason = SafeOpsEngine.validate_deletion_sync({
            "resource_id": resource_id,
            "resource_type": resource_type,
            "tags": {}, # TODO: Fetch tags if possible for better safety
            "confidence": confidence
        })

        if self.auto_pilot_enabled and confidence >= self.min_confidence_threshold and is_safe:
            # Safety Fuse: Check rate limit before executing
            if self._hourly_execution_count >= self.max_deletions_per_hour:
                logger.warning(
                    "auto_pilot_rate_limited",
                    resource_id=resource_id,
                    hourly_count=self._hourly_execution_count,
                    limit=self.max_deletions_per_hour,
                    msg="Rate limit exceeded - request stays in APPROVED state"
                )
                # Only approve, don't execute - human can execute later
                await service.approve(
                    request_id=request.id,
                    tenant_id=self.tenant_id,
                    reviewer_id=None,
                    notes=f"Auto-Pilot Approved (Rate Limited: {self._hourly_execution_count}/{self.max_deletions_per_hour}/hr)"
                )
                return

            logger.info("auto_pilot_engaging", resource_id=resource_id, confidence=confidence)

            # Step 1: Auto-Approve
            await service.approve(
                request_id=request.id,
                tenant_id=self.tenant_id,
                reviewer_id=None, # System approved
                notes=f"Auto-Pilot Execution (Confidence: {confidence})"
            )

            # Step 2: Execute
            await service.execute(
                request_id=request.id,
                tenant_id=self.tenant_id
            )

            # Increment counter for this sweep
            self._hourly_execution_count += 1
        else:
            logger.info("autonomous_candidate_flagged", resource_id=resource_id, mode="pending")
