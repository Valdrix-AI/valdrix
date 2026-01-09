"""
Leaderboards API Endpoints for CloudSentinel.
Shows team savings rankings ("Who saved the most?").
"""
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.models.remediation import RemediationRequest

logger = structlog.get_logger()
router = APIRouter(prefix="/leaderboards", tags=["Leaderboards"])


# ============================================================
# Pydantic Schemas
# ============================================================

class LeaderboardEntry(BaseModel):
    """A single entry in the leaderboard."""
    rank: int
    user_email: str
    savings_usd: float
    remediation_count: int
    
    
class LeaderboardResponse(BaseModel):
    """Leaderboard response with rankings."""
    period: str
    entries: list[LeaderboardEntry]
    total_team_savings: float
    

# ============================================================
# API Endpoints
# ============================================================

@router.get("", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: str = Query("30d", pattern="^(7d|30d|90d|all)$"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the savings leaderboard for the current tenant.
    
    Shows who has approved the most cost-saving remediations.
    
    Args:
        period: Time period - 7d, 30d, 90d, or all
    """
    # Calculate date range
    if period == "all":
        start_date = None
    else:
        days = int(period.replace("d", ""))
        start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query approved remediations grouped by approver
    query = select(
        RemediationRequest.approved_by,
        func.sum(RemediationRequest.estimated_savings).label("total_savings"),
        func.count(RemediationRequest.id).label("count"),
    ).where(
        RemediationRequest.tenant_id == current_user.tenant_id,
        RemediationRequest.status == "approved",
    ).group_by(
        RemediationRequest.approved_by
    ).order_by(
        func.sum(RemediationRequest.estimated_savings).desc()
    )
    
    if start_date:
        query = query.where(RemediationRequest.approved_at >= start_date)
    
    result = await db.execute(query)
    rows = result.fetchall()
    
    # Build leaderboard entries
    entries = []
    total_savings = 0.0
    
    for rank, row in enumerate(rows, start=1):
        savings = float(row.total_savings or 0)
        total_savings += savings
        
        entries.append(LeaderboardEntry(
            rank=rank,
            user_email=row.approved_by or "Unknown",
            savings_usd=savings,
            remediation_count=row.count,
        ))
    
    # If no entries, show encouraging message via empty list
    # Frontend will handle this gracefully
    
    period_labels = {
        "7d": "Last 7 Days",
        "30d": "Last 30 Days",
        "90d": "Last 90 Days",
        "all": "All Time",
    }
    
    return LeaderboardResponse(
        period=period_labels.get(period, "Last 30 Days"),
        entries=entries,
        total_team_savings=total_savings,
    )
