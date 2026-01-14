"""
Safety Settings API

Manages circuit breaker and safety controls for tenants.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Safety"])


# ============================================================
# Pydantic Schemas
# ============================================================

class SafetyStatusResponse(BaseModel):
    """Response for safety/circuit breaker status."""
    circuit_state: str  # "closed", "open", "half_open"
    failure_count: int
    daily_savings_used: float
    daily_savings_limit: float
    last_failure_at: str | None
    can_execute: bool


# ============================================================
# API Endpoints
# ============================================================

@router.get("/safety", response_model=SafetyStatusResponse)
async def get_safety_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get circuit breaker and safety status for the current tenant.
    
    Shows:
    - Circuit state (closed=ok, open=blocked, half_open=testing)
    - Daily savings budget usage
    - Whether remediations can execute
    """
    from app.services.remediation.circuit_breaker import get_circuit_breaker
    from app.core.config import get_settings
    
    settings = get_settings()
    
    try:
        circuit_breaker = await get_circuit_breaker(str(current_user.tenant_id))
        
        state = await circuit_breaker.state.get("state", "closed")
        failure_count = await circuit_breaker.state.get("failure_count", 0)
        daily_savings = await circuit_breaker.state.get("daily_savings", 0.0)
        last_failure = await circuit_breaker.state.get("last_failure_at", None)
        
        can_execute = await circuit_breaker.can_execute()
        
        return SafetyStatusResponse(
            circuit_state=state,
            failure_count=failure_count,
            daily_savings_used=daily_savings,
            daily_savings_limit=settings.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS,
            last_failure_at=last_failure,
            can_execute=can_execute
        )
    except Exception as e:
        logger.error("safety_status_failed", error=str(e))
        # Return safe defaults
        return SafetyStatusResponse(
            circuit_state="unknown",
            failure_count=0,
            daily_savings_used=0.0,
            daily_savings_limit=settings.CIRCUIT_BREAKER_MAX_DAILY_SAVINGS,
            last_failure_at=None,
            can_execute=True
        )


@router.post("/safety/reset")
async def reset_circuit_breaker(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually reset circuit breaker to closed state (admin-only).
    
    Use with caution - this allows remediations to proceed.
    """
    # Check admin role
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    from app.services.remediation.circuit_breaker import get_circuit_breaker
    
    try:
        circuit_breaker = await get_circuit_breaker(str(current_user.tenant_id))
        await circuit_breaker.reset()
        
        logger.info(
            "circuit_breaker_reset",
            tenant_id=str(current_user.tenant_id),
            by_user=str(current_user.id)
        )
        
        return {"status": "reset", "message": "Circuit breaker reset to closed state"}
    except Exception as e:
        logger.error("circuit_breaker_reset_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset circuit breaker"
        ) from e
