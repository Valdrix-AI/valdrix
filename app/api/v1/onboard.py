from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime, timezone
from app.db.session import get_db
from app.core.logging import audit_log
from app.core.auth import get_current_user_from_jwt, CurrentUser
from app.models.tenant import Tenant, User

class OnboardRequest(BaseModel):
    tenant_name: str

router = APIRouter(prefix="/api/v1", tags=["onboarding"])

@router.post("/onboard")
async def onboard(
    request: OnboardRequest,  # Contains: tenant_name
    user: CurrentUser = Depends(get_current_user_from_jwt),  # No DB check
    db: AsyncSession = Depends(get_db),
):
    # 1. Check if user already exists
    existing = await db.execute(select(User).where(User.id == user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Already onboarded")

    # 2. Create Tenant with 14-day trial
    if len(request.tenant_name) < 3:
        raise HTTPException(400, "Tenant name must be at least 3 characters")

    tenant = Tenant(
        name=request.tenant_name,
        plan="trial",
        trial_started_at=datetime.now(timezone.utc)
    )
    db.add(tenant)
    await db.flush()  # Get tenant.id

    # 3. Create User linked to Tenant
    new_user = User(id=user.id, email=user.email, tenant_id=tenant.id, role="owner")
    db.add(new_user)
    await db.commit()

    # 4. Audit Log
    audit_log(
        event="tenant_onboarded",
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        details={"tenant_name": request.tenant_name}
    )

    return {"status": "onboarded", "tenant_id": str(tenant.id)}
