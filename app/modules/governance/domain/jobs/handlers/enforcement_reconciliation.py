from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.enforcement.domain.reconciliation_worker import (
    EnforcementReconciliationWorker,
)
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler


class EnforcementReconciliationHandler(BaseJobHandler):
    """Run tenant-scoped enforcement reservation reconciliation sweep."""

    timeout_seconds = 300

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = job.tenant_id
        if tenant_id is None:
            raise ValueError("tenant_id required for enforcement_reconciliation")

        tenant_uuid = UUID(str(tenant_id))
        result = await EnforcementReconciliationWorker(db).run_for_tenant(tenant_uuid)
        return result.to_payload()

