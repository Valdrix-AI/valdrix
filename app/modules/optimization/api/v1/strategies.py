from typing import Annotated, Any, Dict, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.shared.core.auth import CurrentUser, requires_role, require_tenant_access
from app.shared.db.session import get_db
from app.modules.optimization.domain.service import OptimizationService
from app.models.optimization import StrategyRecommendation, CommitmentTerm, PaymentOption

router = APIRouter(tags=["FinOps Strategy (RI/SP)"])

# --- Schemas ---
class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    resource_type: str
    region: str
    term: CommitmentTerm
    payment_option: PaymentOption
    upfront_cost: float
    monthly_recurring_cost: float
    estimated_monthly_savings_low: float | None = None
    estimated_monthly_savings: float
    estimated_monthly_savings_high: float | None = None
    roi_percentage: float
    break_even_months: float | None = None
    confidence_score: float | None = None
    status: str

class OptimizationScanResponse(BaseModel):
    status: str
    recommendations_generated: int
    message: str

# --- Endpoints ---

@router.get("/recommendations", response_model=List[RecommendationRead])
async def list_recommendations(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="open")
) -> Any:
    """
    List FinOps optimization recommendations for the tenant.
    """
    q = select(StrategyRecommendation).where(
        StrategyRecommendation.tenant_id == tenant_id,
        StrategyRecommendation.status == status
    ).order_by(StrategyRecommendation.estimated_monthly_savings.desc())
    
    result = await db.execute(q)
    return result.scalars().all()

@router.post("/refresh", response_model=OptimizationScanResponse)
async def trigger_optimization_scan(
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
) -> OptimizationScanResponse:
    """
    Trigger a fresh analysis of cloud usage to generate RI/SP recommendations.
    """
    service = OptimizationService(db=db)
    recs = await service.generate_recommendations(tenant_id)
    
    return OptimizationScanResponse(
        status="success",
        recommendations_generated=len(recs),
        message=f"Generated {len(recs)} new optimization opportunities."
    )

@router.post("/apply/{recommendation_id}")
async def apply_recommendation(
    recommendation_id: UUID,
    tenant_id: Annotated[UUID, Depends(require_tenant_access)],
    user: Annotated[CurrentUser, Depends(requires_role("admin"))],
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Mark a recommendation as applied. 
    (Future: Trigger cloud API calls to purchase RI/SP).
    """
    q = select(StrategyRecommendation).where(
        StrategyRecommendation.id == recommendation_id,
        StrategyRecommendation.tenant_id == tenant_id
    )
    result = await db.execute(q)
    rec = result.scalar_one_or_none()
    
    if not rec:
        from app.shared.core.exceptions import ResourceNotFoundError
        raise ResourceNotFoundError("Recommendation not found")

    rec.status = "applied"
    from datetime import datetime, timezone
    rec.applied_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    return {"status": "applied", "recommendation_id": str(recommendation_id)}
