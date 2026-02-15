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


class RemediationHandler(BaseJobHandler):
    """Handle autonomous remediation scan and execution."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.shared.remediation.autonomous import AutonomousRemediationEngine
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        from app.models.aws_connection import AWSConnection
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

            provider_norm = (
                str(getattr(remediation_request, "provider", "aws") or "aws")
                .strip()
                .lower()
            )
            if provider_norm != "aws":
                remediation_request.status = RemediationStatus.FAILED
                remediation_request.execution_error = (
                    "Direct remediation execution currently supports AWS only. "
                    "Use GitOps remediation plans for non-AWS providers."
                )
                await db.commit()
                await db.refresh(remediation_request)
                return {
                    "status": "failed",
                    "mode": "targeted",
                    "request_id": str(remediation_request.id),
                    "remediation_status": remediation_request.status.value,
                    "reason": "provider_not_supported",
                }

            # Resolve AWS connection for credentials (prefer request-scoped connection_id).
            conn_query = select(AWSConnection).where(
                AWSConnection.tenant_id == tenant_id
            )
            if getattr(remediation_request, "connection_id", None):
                conn_query = conn_query.where(
                    AWSConnection.id == remediation_request.connection_id
                )
            conn_query = conn_query.order_by(
                AWSConnection.last_verified_at.desc(), AWSConnection.id.desc()
            )
            conn_res = await db.execute(conn_query)
            connection = conn_res.scalars().first()

            if not connection:
                remediation_request.status = RemediationStatus.FAILED
                remediation_request.execution_error = (
                    "No AWS connection found for this tenant. Setup is required first."
                )
                await db.commit()
                await db.refresh(remediation_request)
                return {
                    "status": "failed",
                    "mode": "targeted",
                    "request_id": str(remediation_request.id),
                    "remediation_status": remediation_request.status.value,
                    "reason": "aws_connection_missing",
                }

            adapter = MultiTenantAWSAdapter(connection)
            creds = await adapter.get_credentials()

            # Prefer request region for execution correctness; fall back to connection default.
            exec_region = (
                str(getattr(remediation_request, "region", "") or "").strip()
                or str(getattr(connection, "region", "") or "").strip()
                or "us-east-1"
            )
            service = RemediationService(db, region=exec_region, credentials=creds)

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
            return {
                "status": "completed",
                "mode": "targeted",
                "request_id": str(result.id),
                "remediation_status": result.status.value,
            }

        # 2. Autonomous Remediation Sweep
        conn_id = payload.get("connection_id")

        # Get AWS connection
        if conn_id:
            db_res = await db.execute(
                select(AWSConnection).where(
                    AWSConnection.id == UUID(conn_id),
                    AWSConnection.tenant_id == tenant_id,
                )
            )
        else:
            db_res = await db.execute(
                select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
            )
        connection = db_res.scalars().first()

        if not connection:
            return {"status": "skipped", "reason": "no_aws_connection"}

        # Get credentials
        adapter = MultiTenantAWSAdapter(connection)
        creds = await adapter.get_credentials()

        engine = AutonomousRemediationEngine(db, str(tenant_id))
        results = await engine.run_autonomous_sweep(
            region=connection.region, credentials=creds
        )

        return {
            "status": "completed",
            "mode": results.get("mode"),
            "scanned": results.get("scanned", 0),
            "auto_executed": results.get("auto_executed", 0),
        }
