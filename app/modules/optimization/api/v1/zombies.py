from typing import Annotated, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import structlog

from app.shared.core.auth import CurrentUser, requires_role, require_tenant_access
from app.shared.db.session import get_db
from app.models.remediation import RemediationAction, RemediationRequest
from app.modules.optimization.domain import ZombieService, RemediationService
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.core.rate_limit import rate_limit, analysis_limit
from app.models.background_job import JobType
from app.modules.governance.domain.jobs.processor import enqueue_job

router = APIRouter(tags=["Cloud Hygiene (Zombies)"])
logger = structlog.get_logger()

# --- Schemas ---
class RemediationRequestCreate(BaseModel):
    resource_id: str
    resource_type: str
    action: str
    provider: str = "aws"
    connection_id: Optional[UUID] = None
    estimated_savings: float
    create_backup: bool = False
    backup_retention_days: int = 30
    backup_cost_estimate: float = 0

class ReviewRequest(BaseModel):
    notes: Optional[str] = None

# --- Endpoints ---

@router.get("")
@rate_limit("10/minute") # type: ignore[untyped-decorator]
async def scan_zombies(
    request: Request,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
    analyze: bool = Query(default=False, description="Enable AI-powered analysis of detected zombies"),
    background: bool = Query(default=False, description="Run scan as a background job"),
) -> Any:
    """
    Scan cloud accounts for zombie resources.
    If background=True, returns a job_id immediately.
    """
    if background:
        logger.info("enqueuing_zombie_scan", tenant_id=str(tenant_id), region=region)
        job = await enqueue_job(
            db=db,
            job_type=JobType.ZOMBIE_SCAN,
            tenant_id=tenant_id,
            payload={
                "region": region,
                "analyze": analyze
            }
        )
        return {"status": "pending", "job_id": str(job.id)}

    service = ZombieService(db=db)
    return await service.scan_for_tenant(
        tenant_id=tenant_id,
        _user=user,
        region=region,
        analyze=analyze
    )

@router.post("/request")
async def create_remediation_request(
    request: RemediationRequestCreate,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.AUTO_REMEDIATION))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
) -> Dict[str, str]:
    """Create a remediation request. Requires Pro tier or higher."""
    try:
        action_enum = RemediationAction(request.action)
    except ValueError:
        from app.shared.core.exceptions import ValdrixException
        raise ValdrixException(
            message=f"Invalid action: {request.action}",
            code="invalid_remediation_action",
            status_code=400
        )

    service = RemediationService(db=db, region=region)
    result = await service.create_request(
        tenant_id=tenant_id,
        user_id=user.id,
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        action=action_enum,
        estimated_savings=request.estimated_savings,
        create_backup=request.create_backup,
        backup_retention_days=request.backup_retention_days,
        backup_cost_estimate=request.backup_cost_estimate,
        provider=request.provider,
        connection_id=request.connection_id,
    )
    return {"status": "pending", "request_id": str(result.id)}

@router.get("/pending")
async def list_pending_requests(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """List pending requests."""
    service = RemediationService(db=db, region=region)
    pending = await service.list_pending(tenant_id, limit=limit, offset=offset)
    return {
        "pending_count": len(pending),
        "requests": [
            {
                "id": str(r.id),
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "action": r.action.value,
                "estimated_savings": float(r.estimated_monthly_savings or 0),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in pending
        ]
    }

@router.post("/approve/{request_id}")
async def approve_remediation(
    request_id: UUID,
    review: ReviewRequest,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
) -> Dict[str, str]:
    """Approve a request."""
    service = RemediationService(db=db, region=region)
    try:
        result = await service.approve(request_id, tenant_id, user.id, review.notes)
        return {"status": "approved", "request_id": str(result.id)}
    except ValueError as e:
        from app.shared.core.exceptions import ResourceNotFoundError
        raise ResourceNotFoundError(str(e), code="remediation_request_not_found")

@router.post("/execute/{request_id}")
@analysis_limit
async def execute_remediation(
    request: Request,
    request_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
    bypass_grace_period: bool = Query(default=False, description="Bypass 24h grace period (emergency use)"),
) -> Dict[str, str]:
    """Execute a remediation request. Requires Pro tier or higher and Admin role."""
    # Note: requires_feature(FeatureFlag.AUTO_REMEDIATION) also checks for isAdmin if we wanted, 
    # but here we use requires_role("admin") explicitly for SEC-02.

    from app.models.aws_connection import AWSConnection
    from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
    
    result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id))
    connection = result.scalar_one_or_none()
    if not connection:
        from app.shared.core.exceptions import ValdrixException
        raise ValdrixException(
            message="No AWS connection found for this tenant. Setup is required first.",
            code="aws_connection_missing",
            status_code=400
        )

    adapter = MultiTenantAWSAdapter(connection)
    credentials = await adapter.get_credentials() 
    service = RemediationService(db=db, region=region, credentials=credentials)

    try:
        executed_request = await service.execute(request_id, tenant_id, bypass_grace_period=bypass_grace_period)
        return {"status": executed_request.status.value, "request_id": str(executed_request.id)}
    except ValueError as e:
        from app.shared.core.exceptions import ValdrixException
        raise ValdrixException(
            message=str(e),
            code="remediation_execution_failed",
            status_code=400
        )

@router.get("/plan/{request_id}")
async def get_remediation_plan(
    request_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_feature(FeatureFlag.GITOPS_REMEDIATION))],
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate and return a Terraform decommissioning plan for a remediation request.
    Requires Pro tier or higher.
    """
    service = RemediationService(db=db)
    
    # Fetch the request
    result = await db.execute(
        select(RemediationRequest)
        .where(RemediationRequest.id == request_id)
        .where(RemediationRequest.tenant_id == tenant_id)
    )
    remediation_request = result.scalar_one_or_none()
    
    if not remediation_request:
        from app.shared.core.exceptions import ResourceNotFoundError
        raise ResourceNotFoundError(f"Remediation request {request_id} not found")
        
    plan = await service.generate_iac_plan(remediation_request, tenant_id)
    
    return {
        "status": "success",
        "plan": plan,
        "resource_id": remediation_request.resource_id,
        "provider": remediation_request.provider
    }
