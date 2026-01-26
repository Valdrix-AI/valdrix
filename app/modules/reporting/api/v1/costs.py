from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from typing import Optional, Dict, Any, List
from app.shared.db.session import get_db
from app.shared.core.auth import get_current_user
from app.modules.reporting.domain.aggregator import CostAggregator
from app.models.tenant import User
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.factory import LLMFactory
from app.shared.core.pricing import PricingTier, requires_tier

router = APIRouter(tags=["Costs"])

@router.get("")
async def get_costs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns aggregated cost metrics for the selected time period.
    Supports filtering by provider (aws, azure, gcp).
    """
    return await CostAggregator.get_dashboard_summary(
        db, current_user.tenant_id, start_date, end_date, provider
    )

@router.get("/breakdown")
async def get_cost_breakdown(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Provides a service-level cost breakdown."""
    return await CostAggregator.get_basic_breakdown(
        db, current_user.tenant_id, start_date, end_date, provider
    )

@router.get("/forecast")
async def get_cost_forecast(
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Generates a cost forecast using the Symbolic Forecasting engine.
    """
    from app.shared.analysis.forecaster import SymbolicForecaster
    
    # Fetch last 30 days for forecasting context
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    
    summary = await CostAggregator.get_summary(
        db, current_user.tenant_id, start_date, end_date
    )
    
    if not summary.records:
        raise HTTPException(status_code=400, detail="Insufficient cost history for forecasting.")
        
    return await SymbolicForecaster.forecast(
        summary.records, 
        days=days,
        db=db,
        tenant_id=current_user.tenant_id
    )

@router.post("/analyze")
@requires_tier(PricingTier.GROWTH, PricingTier.PRO, PricingTier.ENTERPRISE)
async def analyze_costs(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Triggers an AI-powered analysis of the cost data.
    Requires Growth tier or higher.
    """
    # 1. Fetch data
    summary = await CostAggregator.get_summary(
        db, current_user.tenant_id, start_date, end_date, provider
    )
    
    if not summary.records:
        return {
            "summary": "No cost data available for analysis.",
            "anomalies": [],
            "recommendations": [],
            "estimated_total_savings": 0.0
        }

    # 2. Initialize LLM
    llm = LLMFactory.create()
    analyzer = FinOpsAnalyzer(llm, db)
    
    # 3. Analyze
    result = await analyzer.analyze(
        usage_summary=summary,
        tenant_id=current_user.tenant_id,
        db=db,
        provider=provider
    )
    
    return result

@router.post("/ingest")
async def trigger_ingest(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Manually triggers cost ingestion for active cloud connections.
    """
    from app.modules.governance.domain.jobs.processor import enqueue_job
    from app.models.background_job import JobType
    
    job = await enqueue_job(
        db=db,
        tenant_id=current_user.tenant_id,
        job_type=JobType.COST_INGESTION,
        payload={}
    )
    return {"status": "queued", "job_id": str(job.id)}
