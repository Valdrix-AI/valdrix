from typing import Annotated, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import structlog

from app.core.auth import CurrentUser, requires_role
from app.db.session import get_db
from app.models.aws_connection import AWSConnection
from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.models.remediation import RemediationAction
from app.core.tier_guard import TierGuard, FeatureFlag
from app.services.zombies import ZombieService, RemediationService

router = APIRouter(prefix="/zombies", tags=["Cloud Hygiene (Zombies)"])
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
async def scan_zombies(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
    analyze: bool = Query(default=False, description="Enable AI-powered analysis of detected zombies"),
):
    """
    Scan cloud accounts for zombie resources.
    """
    service = ZombieService(db)
    return await service.scan_for_tenant(
        tenant_id=user.tenant_id,
        user=user,
        region=region,
        analyze=analyze
    )

@router.post("/request")
async def create_remediation_request(
    request: RemediationRequestCreate,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """Create a remediation request. Requires Pro tier or higher."""
    async with TierGuard(user, db) as guard:
        if not guard.has(FeatureFlag.AUTO_REMEDIATION):
            raise HTTPException(
                status_code=403,
                detail="Auto-remediation requires Pro tier or higher. Please upgrade."
            )
    
    try:
        action_enum = RemediationAction(request.action)
    except ValueError:
        raise HTTPException(400, f"Invalid action: {request.action}")

    service = RemediationService(db=db, region=region)
    result = await service.create_request(
        tenant_id=user.tenant_id,
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
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """List pending requests."""
    service = RemediationService(db=db, region=region)
    pending = await service.list_pending(user.tenant_id)
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
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """Approve a request."""
    service = RemediationService(db=db, region=region)
    try:
        result = await service.approve(request_id, user.tenant_id, user.id, review.notes)
        return {"status": "approved", "request_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(404, str(e))

@router.post("/execute/{request_id}")
async def execute_remediation(
    request_id: UUID,
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """Execute a remediation request. Requires Pro tier or higher."""
    async with TierGuard(user, db) as guard:
        if not guard.has(FeatureFlag.AUTO_REMEDIATION):
            raise HTTPException(
                status_code=403,
                detail="Auto-remediation requires Pro tier or higher. Please upgrade."
            )

    result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == user.tenant_id))
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(400, "No AWS connection")

    adapter = MultiTenantAWSAdapter(connection)
    # Refactored: Fetching credentials via public service/adapter methods if needed, 
    # but here we pass them to RemediationService.
    # TODO: Refactor RemediationService to fetch credentials internally using connection_id
    credentials = await adapter.get_credentials() 
    service = RemediationService(db=db, region=region, credentials=credentials)

    try:
        result = await service.execute(request_id, user.tenant_id)
        return {"status": result.status.value, "request_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(400, str(e))
