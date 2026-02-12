"""
Dunning Job Handler

Processes scheduled dunning retry jobs for failed payments.
"""
from typing import Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler


class DunningHandler(BaseJobHandler):
    """
    Process a dunning retry - attempt to charge the subscription again.
    
    Called by JobProcessor when a DUNNING job is due for execution.
    """
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.billing.domain.billing.dunning_service import DunningService
        
        payload = job.payload or {}
        sub_id = payload.get("subscription_id")
        attempt = payload.get("attempt", 1)
        
        if not sub_id:
            raise ValueError("subscription_id required for dunning")
        
        dunning = DunningService(db)
        result = await dunning.retry_payment(UUID(sub_id))
        
        return {
            "status": result.get("status"),
            "attempt": attempt,
            **result
        }
