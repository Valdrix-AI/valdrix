"""
License Governance Job Handler
"""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.modules.optimization.domain.license_governance import LicenseGovernanceService


class LicenseGovernanceHandler(BaseJobHandler):
    """Run tenant-scoped license governance sweep via the domain service."""

    timeout_seconds = 300

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise ValueError("tenant_id required for license_governance")

        tenant_uuid = UUID(str(tenant_id))
        result = await LicenseGovernanceService(db).run_tenant_governance(tenant_uuid)

        if isinstance(result, dict):
            payload = dict(result)
        else:
            payload = {"status": "completed", "result": result}

        payload.setdefault("tenant_id", str(tenant_uuid))
        return payload

