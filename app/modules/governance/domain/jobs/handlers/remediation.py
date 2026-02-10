"""
Remediation Job Handlers
"""
from typing import Dict, Any
from uuid import UUID
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
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for remediation")
            
        payload = job.payload or {}
        request_id = payload.get("request_id")
        
        # 1. Targeted Remediation (Single Resource Approval)
        if request_id:
            from app.modules.optimization.domain.remediation import RemediationService
            service = RemediationService(db)
            result = await service.execute(UUID(request_id), tenant_id)
            return {
                "status": "completed",
                "mode": "targeted",
                "request_id": str(result.id),
                "remediation_status": result.status.value
            }

        # 2. Autonomous Remediation Sweep
        conn_id = payload.get("connection_id")
        
        # Get AWS connection
        if conn_id:
            db_res = await db.execute(
                select(AWSConnection).where(
                    AWSConnection.id == UUID(conn_id),
                    AWSConnection.tenant_id == tenant_id
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
        results = await engine.run_autonomous_sweep(region=connection.region, credentials=creds)
        
        return {
            "status": "completed",
            "mode": results.get("mode"),
            "scanned": results.get("scanned", 0),
            "auto_executed": results.get("auto_executed", 0)
        }
