"""
License Governance Tasks - Periodic SaaS/License auditing.
"""

from typing import Any
import structlog
from celery import shared_task
from app.shared.db.session import async_session_maker
from app.models.tenant import Tenant
from app.modules.optimization.domain.license_governance import LicenseGovernanceService
from app.tasks.scheduler_tasks import run_async, _open_db_session
import sqlalchemy as sa
import time

logger = structlog.get_logger()


@shared_task(
    name="license.governance_sweep",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 1, "countdown": 3600},
)
def run_license_governance_sweep() -> None:
    """
    Periodic task to trigger license governance for all tenants.
    """
    run_async(_license_governance_sweep_logic)


async def _license_governance_sweep_logic() -> None:
    job_name = "license_governance_sweep"
    start_time = time.time()
    
    try:
        async with _open_db_session() as db:
            # Fetch all tenants to run governance for.
            # In a larger system, we'd cohort this as we do in scheduler_tasks.py
            result = await db.execute(sa.select(Tenant.id))
            tenant_ids = result.scalars().all()
            
            for tid in tenant_ids:
                # Dispatch per-tenant governance task
                run_tenant_license_governance.delay(str(tid))
                
            logger.info("license_governance_sweep_dispatched", count=len(tenant_ids))
            
    except Exception as e:
        logger.error("license_governance_sweep_failed", error=str(e))
        raise


@shared_task(
    name="license.tenant_governance",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
)
def run_tenant_license_governance(tenant_id: str) -> None:
    """
    Runs license governance logic for a specific tenant.
    """
    run_async(_tenant_license_governance_logic, tenant_id)


async def _tenant_license_governance_logic(tenant_id: str) -> None:
    async with _open_db_session() as db:
        service = LicenseGovernanceService(db)
        await service.run_tenant_governance(tenant_id)
