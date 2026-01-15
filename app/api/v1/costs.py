from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.auth import CurrentUser, requires_role
from app.db.session import get_db
from app.models.aws_connection import AWSConnection
from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.services.llm.analyzer import FinOpsAnalyzer

from app.models.llm import LLMUsage
from app.core.dependencies import get_analyzer
from app.core.pricing import PricingTier, is_feature_enabled
from pydantic import BaseModel
from typing import Any

class CostResponse(BaseModel):
    analysis: Any

router = APIRouter(tags=["Costs & Analysis"])
logger = structlog.get_logger()


@router.get("/costs")
async def get_costs(
    start_date: date,
    end_date: date,
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """Retrieves daily cloud costs for a specified date range."""
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == user.tenant_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        logger.warning("no_aws_connection", tenant_id=str(user.tenant_id))
        return {
            "total_cost": 0,
            "breakdown": [],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "error": "No AWS connection found.",
        }

    adapter = MultiTenantAWSAdapter(connection)
    results = await adapter.get_daily_costs(start_date, end_date)

    # Simple total calculation for response
    total = Decimal("0")
    if results and not (isinstance(results[0], dict) and "Error" in results[0]):
        # results logic is a bit mixed, checking if it's CloudUsageSummary vs list of dicts
        if hasattr(results, "total_cost"):
            total = results.total_cost
        else:
            for day in results:
                # AWS Cost Explorer format: day['Total']['UnblendedCost']['Amount']
                for metric in day.get("Total", {}).values():
                    total += Decimal(metric.get("Amount", 0))

    return {
        "total_cost": total,
        "breakdown": results,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }





@router.get("/current", response_model=CostResponse)
async def analyze_costs(
    start_date: date,
    end_date: date,
    analyzer: Annotated[FinOpsAnalyzer, Depends(get_analyzer)],
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
):
    """AI-powered analysis of cloud costs. Requires Growth tier or higher."""
    # Feature gating: Check tier access
    user_tier = getattr(user, "tier", "starter")
    try:
        tier_enum = PricingTier(user_tier)
    except ValueError:
        tier_enum = PricingTier.STARTER

    if not is_feature_enabled(tier_enum, "llm_analysis"):
        return {
            "analysis": "AI-powered analysis requires Growth tier or higher.",
            "upgrade_required": True,
            "current_tier": user_tier,
        }
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == user.tenant_id)
    )
    connection = result.scalar_one_or_none()

    if not connection:
        return {"analysis": "No AWS connection found."}

    adapter = MultiTenantAWSAdapter(connection)
    cost_data = await adapter.get_daily_costs(start_date, end_date)

    logger.info("starting_sentinel_analysis", start=start_date, end=end_date)

    insights = await analyzer.analyze(
        cost_data,
        tenant_id=user.tenant_id,
        db=db,
    )

    return {"analysis": insights}


@router.get("/llm/usage")
async def get_llm_usage(
    user: Annotated[CurrentUser, Depends(requires_role("member"))],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    """Get LLM usage history for the tenant."""
    result = await db.execute(
        select(LLMUsage)
        .where(LLMUsage.tenant_id == user.tenant_id)
        .order_by(LLMUsage.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()

    return {
        "usage": [
            {
                "id": str(r.id),
                "model": r.model,
                "provider": r.provider,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": float(r.cost_usd) if r.cost_usd else 0,
                "request_type": r.request_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "count": len(records),
    }
