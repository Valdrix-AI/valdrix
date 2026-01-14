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
from app.services.zombies import ZombieDetector, RemediationService
from app.models.remediation import RemediationAction

router = APIRouter(prefix="/zombies", tags=["Cloud Hygiene (Zombies)"])
logger = structlog.get_logger()

# --- Schemas ---
class RemediationRequestCreate(BaseModel):
    resource_id: str
    resource_type: str
    action: str
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
    Scan AWS account for zombie resources.

    Args:
        analyze: If True, enriches results with LLM-generated explanations and recommendations.
                 This uses tokens and will be tracked in LLM usage.
    """
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == user.tenant_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return {
            "unattached_volumes": [],
            "old_snapshots": [],
            "unused_elastic_ips": [],
            "error": "No AWS connection found."
        }

    adapter = MultiTenantAWSAdapter(connection)
    credentials = await adapter._get_credentials()

    detector = ZombieDetector(region=region, credentials=credentials)
    zombies = await detector.scan_all()

    # AI Analysis (optional, requires Starter+ tier)
    if analyze:
        try:
            from app.core.tier_guard import TierGuard, FeatureFlag
            
            async with TierGuard(user, db) as guard:
                if not guard.has(FeatureFlag.AI_INSIGHTS):
                    zombies["ai_analysis"] = {
                        "error": "AI Insights requires Starter tier or higher.",
                        "summary": "Upgrade to unlock AI-powered analysis.",
                        "upgrade_required": True
                    }
                else:
                    from app.services.llm.factory import LLMFactory
                    from app.services.llm.zombie_analyzer import ZombieAnalyzer

                    llm = LLMFactory.create()
                    analyzer = ZombieAnalyzer(llm)

                    ai_analysis = await analyzer.analyze(
                        detection_results=zombies,
                        tenant_id=user.tenant_id,
                        db=db,
                    )
                    zombies["ai_analysis"] = ai_analysis
                    logger.info("zombie_ai_analysis_complete",
                               resource_count=len(ai_analysis.get("resources", [])))
        except Exception as e:
            logger.error("zombie_ai_analysis_failed", error=str(e))
            zombies["ai_analysis"] = {
                "error": f"AI analysis failed: {str(e)}",
                "summary": "Analysis unavailable. Rule-based detection completed successfully."
            }

    # Notification logic - use centralized helper
    try:
        from app.services.notifications import get_slack_service
        slack = get_slack_service()
        if slack:
            estimated_savings = zombies.get("total_monthly_waste", 0.0)
            await slack.notify_zombies(zombies, estimated_savings)
    except Exception as e:
        logger.error("zombie_slack_alert_failed", error=str(e))

    return zombies

@router.post("/request")
async def create_remediation_request(
    request: RemediationRequestCreate,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """Create a remediation request. Requires Pro tier or higher."""
    from app.core.pricing import PricingTier, is_feature_enabled
    
    # Feature gating: Pro+ required for auto-remediation
    user_tier = getattr(user, "tier", "starter")
    try:
        tier_enum = PricingTier(user_tier)
    except ValueError:
        tier_enum = PricingTier.STARTER
    
    if not is_feature_enabled(tier_enum, "auto_remediation"):
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
    from app.core.pricing import PricingTier, is_feature_enabled
    
    # Feature gating: Pro+ required
    user_tier = getattr(user, "tier", "starter")
    try:
        tier_enum = PricingTier(user_tier)
    except ValueError:
        tier_enum = PricingTier.STARTER
    
    if not is_feature_enabled(tier_enum, "auto_remediation"):
        raise HTTPException(
            status_code=403,
            detail="Auto-remediation requires Pro tier or higher. Please upgrade."
        )
    result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == user.tenant_id))
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(400, "No AWS connection")

    adapter = MultiTenantAWSAdapter(connection)
    credentials = await adapter._get_credentials()
    service = RemediationService(db=db, region=region, credentials=credentials)

    try:
        result = await service.execute(request_id, user.tenant_id)
        return {"status": result.status.value, "request_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(400, str(e))
