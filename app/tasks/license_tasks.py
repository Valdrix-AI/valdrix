"""
License Governance Tasks - Periodic SaaS/License auditing.
"""

from datetime import datetime, timezone
from uuid import UUID

import asyncio
import inspect
import httpx
import structlog
import sqlalchemy as sa
from celery import shared_task
from sqlalchemy.dialects.postgresql import insert

from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.tenant import Tenant
from app.modules.governance.domain.scheduler.metrics import (
    BACKGROUND_JOBS_ENQUEUED_SCHEDULER as BACKGROUND_JOBS_ENQUEUED,
)
from app.modules.optimization.domain.license_governance import LicenseGovernanceService
from app.shared.core.exceptions import ExternalAPIError
from app.tasks.scheduler_tasks import _open_db_session, run_async

logger = structlog.get_logger()

_RETRYABLE_LICENSE_TASK_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
    sa.exc.DBAPIError,
    ExternalAPIError,
    httpx.TimeoutException,
    httpx.TransportError,
)


@shared_task(  # type: ignore[untyped-decorator]
    name="license.governance_sweep",
    autoretry_for=_RETRYABLE_LICENSE_TASK_EXCEPTIONS,
    retry_kwargs={"max_retries": 1, "countdown": 3600},
)
def run_license_governance_sweep() -> None:
    """
    Periodic task to trigger license governance for all tenants.
    """
    run_async(_license_governance_sweep_logic)


async def _license_governance_sweep_logic() -> None:
    try:
        async with _open_db_session() as db:
            begin_ctx = db.begin()
            if (
                asyncio.iscoroutine(begin_ctx)
                or inspect.isawaitable(begin_ctx)
            ) and (
                not hasattr(begin_ctx, "__aenter__")
            ):
                begin_ctx = await begin_ctx
            async with begin_ctx:
                result = await db.execute(
                    sa.select(Tenant.id).with_for_update(skip_locked=True)
                )
                tenant_ids = result.scalars().all()
                now = datetime.now(timezone.utc)
                bucket_str = now.strftime("%Y-%m-%d")
                jobs_enqueued = 0

                for tenant_id in tenant_ids:
                    dedup_key = (
                        f"{tenant_id}:{JobType.LICENSE_GOVERNANCE.value}:{bucket_str}"
                    )
                    stmt = (
                        insert(BackgroundJob)
                        .values(
                            job_type=JobType.LICENSE_GOVERNANCE.value,
                            tenant_id=tenant_id,
                            status=JobStatus.PENDING.value,
                            scheduled_for=now,
                            created_at=now,
                            deduplication_key=dedup_key,
                            priority=0,
                        )
                        .on_conflict_do_nothing(index_elements=["deduplication_key"])
                    )
                    result_proxy = await db.execute(stmt)
                    if (
                        hasattr(result_proxy, "rowcount")
                        and result_proxy.rowcount > 0
                    ):
                        jobs_enqueued += 1
                        BACKGROUND_JOBS_ENQUEUED.labels(
                            job_type=JobType.LICENSE_GOVERNANCE.value,
                            cohort="LICENSE",
                        ).inc()

                logger.info(
                    "license_governance_sweep_enqueued",
                    tenants=len(tenant_ids),
                    jobs_enqueued=jobs_enqueued,
                    bucket=bucket_str,
                )

    except Exception as e:
        logger.error("license_governance_sweep_failed", error=str(e))
        raise


@shared_task(  # type: ignore[untyped-decorator]
    name="license.tenant_governance",
    autoretry_for=_RETRYABLE_LICENSE_TASK_EXCEPTIONS,
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
        await service.run_tenant_governance(UUID(tenant_id))
