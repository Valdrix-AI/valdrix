"""
Remediation Job Handlers
"""

from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.shared.core.remediation_results import (
    normalize_remediation_status,
    parse_remediation_execution_error,
)


def _normalize_remediation_execution_result(
    request_id: UUID,
    remediation_status: str,
    execution_error: str | None,
) -> Dict[str, Any]:
    """
    Map remediation execution result to explicit job handler payload semantics.

    - completed remediation => status=completed
    - failed remediation => status=failed with parsed reason
    - any other remediation state => status set to that state
    """
    if remediation_status == "completed":
        return {
            "status": "completed",
            "mode": "targeted",
            "request_id": str(request_id),
            "remediation_status": remediation_status,
        }

    if remediation_status == "failed":
        failure = parse_remediation_execution_error(execution_error)
        response: Dict[str, Any] = {
            "status": "failed",
            "mode": "targeted",
            "request_id": str(request_id),
            "remediation_status": remediation_status,
            "reason": failure.reason,
            "error": failure.message,
        }
        if failure.status_code is not None:
            response["status_code"] = failure.status_code
        return response

    return {
        "status": remediation_status,
        "mode": "targeted",
        "request_id": str(request_id),
        "remediation_status": remediation_status,
    }


class RemediationHandler(BaseJobHandler):
    """Handle autonomous remediation scan and execution."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.shared.remediation.autonomous import AutonomousRemediationEngine
        from app.models.remediation import RemediationRequest, RemediationStatus

        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for remediation")

        payload = job.payload or {}
        request_id = payload.get("request_id")

        # 1. Targeted Remediation (Single Resource Approval)
        if request_id:
            from app.modules.optimization.domain.remediation import RemediationService
            from app.shared.core.exceptions import ResourceNotFoundError

            request_uuid = UUID(str(request_id))
            remediation_res = await db.execute(
                select(RemediationRequest).where(
                    RemediationRequest.id == request_uuid,
                    RemediationRequest.tenant_id == tenant_id,
                )
            )
            remediation_request = remediation_res.scalar_one_or_none()
            if not remediation_request:
                raise ResourceNotFoundError(
                    f"Remediation request {request_id} not found",
                    code="remediation_request_not_found",
                )

            # Prefer request region; if missing use global hint so service can resolve from connection context.
            default_region = "global"
            exec_region = (
                str(getattr(remediation_request, "region", "") or "").strip()
                or default_region
            )
            service = RemediationService(db, region=exec_region)

            # If a scheduled job runs early due to clock skew, reschedule instead of marking complete.
            scheduled_at = getattr(remediation_request, "scheduled_execution_at", None)
            if (
                remediation_request.status == RemediationStatus.SCHEDULED
                and isinstance(scheduled_at, datetime)
                and datetime.now(timezone.utc) < scheduled_at
            ):
                return {
                    "status": "skipped",
                    "mode": "targeted",
                    "request_id": str(remediation_request.id),
                    "remediation_status": remediation_request.status.value,
                    "reason": "grace_period_not_elapsed",
                    "scheduled_execution_at": scheduled_at.isoformat(),
                }

            result = await service.execute(request_uuid, tenant_id)
            remediation_status = normalize_remediation_status(result.status)
            return _normalize_remediation_execution_result(
                request_id=result.id,
                remediation_status=remediation_status,
                execution_error=getattr(result, "execution_error", None),
            )

        # 2. Autonomous Remediation Sweep
        conn_id = payload.get("connection_id")
        engine = AutonomousRemediationEngine(db, str(tenant_id))
        region = str(payload.get("region") or "global")
        results = await engine.run_autonomous_sweep(
            region=region,
            credentials=None,
            connection_id=conn_id,
        )
        if results.get("error") == "no_connections_found":
            return {"status": "skipped", "reason": "no_connections_found"}

        return {
            "status": "completed",
            "mode": results.get("mode"),
            "scanned": results.get("scanned", 0),
            "auto_executed": results.get("auto_executed", 0),
        }
