"""
Temporal Workflow Definitions for Distributed Task Execution

Replaces APScheduler with durable, resumable workflows.
Benefits:
- Survives crashes and restarts
- Built-in retry with exponential backoff
- Workflow visibility dashboard
- Idempotent by design

Requirements:
- pip install temporalio
- Temporal server: docker-compose (or Temporal Cloud)
"""

from datetime import timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
import structlog

# Temporal imports (soft dependency)
try:
    from temporalio import workflow, activity
    from temporalio.client import Client
    TEMPORAL_AVAILABLE = True
except ImportError:
    TEMPORAL_AVAILABLE = False
    # Create stubs for type hints
    workflow = None
    activity = None

logger = structlog.get_logger()


@dataclass
class TenantScanInput:
    """Input for a single tenant scan."""
    tenant_id: str
    aws_connection_id: str
    regions: List[str]


@dataclass
class ScanResult:
    """Result from scanning a tenant."""
    tenant_id: str
    total_waste: float
    zombies_found: int
    regions_scanned: int
    errors: List[str]


if TEMPORAL_AVAILABLE:
    @activity.defn
    async def scan_tenant_activity(input: TenantScanInput) -> ScanResult:
        """
        Activity: Scan a single tenant's AWS account for zombies.

        This is idempotent - safe to retry on failure.
        """
        from app.services.zombies.detector import ZombieDetector

        logger.info("temporal_activity_start",
                   tenant_id=input.tenant_id,
                   regions=len(input.regions))

        try:
            # Use existing detector logic
            detector = ZombieDetector(region=input.regions[0])
            results = await detector.scan_all_regions(input.regions)

            return ScanResult(
                tenant_id=input.tenant_id,
                total_waste=results.get("total_monthly_waste", 0),
                zombies_found=sum(len(r.get("items", [])) for r in results.get("regions", [])),
                regions_scanned=len(input.regions),
                errors=results.get("errors", [])
            )

        except Exception as e:
            logger.error("temporal_activity_failed",
                        tenant_id=input.tenant_id,
                        error=str(e))
            return ScanResult(
                tenant_id=input.tenant_id,
                total_waste=0,
                zombies_found=0,
                regions_scanned=0,
                errors=[str(e)]
            )


    @workflow.defn
    class DailyAnalysisWorkflow:
        """
        Durable workflow that runs daily analysis for all tenants.

        Features:
        - Survives crashes (resumes from last checkpoint)
        - Per-tenant isolation (one failure doesn't affect others)
        - Visibility into execution progress
        """

        @workflow.run
        async def run(self, tenant_inputs: List[TenantScanInput]) -> Dict[str, Any]:
            """Execute daily analysis for all tenants."""

            results = []
            errors = []

            for input in tenant_inputs:
                try:
                    # Each activity has its own retry policy
                    result = await workflow.execute_activity(
                        scan_tenant_activity,
                        input,
                        start_to_close_timeout=timedelta(minutes=10),
                        retry_policy=workflow.RetryPolicy(
                            initial_interval=timedelta(seconds=10),
                            maximum_interval=timedelta(minutes=5),
                            maximum_attempts=3,
                        )
                    )
                    results.append(result)

                except Exception as e:
                    errors.append({
                        "tenant_id": input.tenant_id,
                        "error": str(e)
                    })

            return {
                "tenants_scanned": len(results),
                "total_errors": len(errors),
                "total_waste_found": sum(r.total_waste for r in results),
                "results": [vars(r) for r in results],
                "errors": errors
            }


    @workflow.defn
    class RemediationWorkflow:
        """
        Durable workflow for executing remediation with safety checks.

        Why Temporal for remediation:
        - Ensures exactly-once execution (no duplicate deletions)
        - Tracks full execution history for audit
        - Supports human-in-the-loop approval
        """

        @workflow.run
        async def run(self, remediation_id: str, action: str) -> Dict[str, Any]:
            """Execute remediation with full audit trail."""

            # Step 1: Validate request still valid
            # Step 2: Create backup if configured
            # Step 3: Execute action
            # Step 4: Verify success
            # Step 5: Log to audit

            # This is a scaffold - full implementation integrates with
            # RemediationService and AuditLogger

            return {
                "remediation_id": remediation_id,
                "status": "completed",
                "action": action
            }


class TemporalClient:
    """
    Client wrapper for Temporal integration.

    Usage:
        client = await TemporalClient.connect()
        await client.start_daily_analysis(tenant_inputs)
    """

    def __init__(self, client: "Client"):
        self._client = client

    @classmethod
    async def connect(cls, host: str = "localhost:7233") -> "TemporalClient":
        """Connect to Temporal server."""
        if not TEMPORAL_AVAILABLE:
            raise ImportError("temporalio not installed. Run: pip install temporalio")

        client = await Client.connect(host)
        return cls(client)

    async def start_daily_analysis(
        self,
        tenant_inputs: List[TenantScanInput]
    ) -> str:
        """Start daily analysis workflow, returns workflow ID."""

        handle = await self._client.start_workflow(
            DailyAnalysisWorkflow.run,
            tenant_inputs,
            id=f"daily-analysis-{workflow.now().isoformat()}",
            task_queue="valdrix-analysis"
        )

        return handle.id
