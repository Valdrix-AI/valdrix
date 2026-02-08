from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timezone
import structlog

from app.shared.db.session import get_db
from app.shared.core.logging import audit_log
from app.shared.core.auth import get_current_user_from_jwt, CurrentUser, UserRole
from app.models.tenant import Tenant, User
from app.shared.core.pricing import PricingTier
from app.shared.core.rate_limit import auth_limit

logger = structlog.get_logger()

class OnboardRequest(BaseModel):
    tenant_name: str = Field(..., min_length=3, max_length=100)
    admin_email: EmailStr | None = None
    cloud_config: Dict[str, Any] | None = Field(None, description="Optional cloud credentials for immediate verification")

class OnboardResponse(BaseModel):
    status: str
    tenant_id: UUID

router = APIRouter(tags=["onboarding"])

@router.post("", response_model=OnboardResponse)
@auth_limit
async def onboard(
    request: Request,
    onboard_req: OnboardRequest,
    user: CurrentUser = Depends(get_current_user_from_jwt),  # No DB check
    db: AsyncSession = Depends(get_db),
):
    # 1. Check if user already exists
    existing = await db.execute(select(User).where(User.id == user.id))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Already onboarded")

    # 2. Create Tenant with 14-day trial
    if len(onboard_req.tenant_name) < 3:
        raise HTTPException(400, "Tenant name must be at least 3 characters")

    tenant = Tenant(
        name=onboard_req.tenant_name,
        plan=PricingTier.TRIAL.value,
        trial_started_at=datetime.now(timezone.utc)
    )

    # 3. Active Credential Validation (Hardening)
    if onboard_req.cloud_config:
        platform = onboard_req.cloud_config.get("platform", "").lower()
        logger.info("verifying_initial_cloud_connection", platform=platform)
        
        try:
            from app.shared.adapters.factory import AdapterFactory
            from app.models.aws_connection import AWSConnection
            from app.models.azure_connection import AzureConnection
            from app.models.gcp_connection import GCPConnection
            
            # Create a mock/temporary connection object for verification
            conn = None
            if platform == "aws":
                conn = AWSConnection(
                    role_arn=onboard_req.cloud_config.get("role_arn"),
                    external_id=onboard_req.cloud_config.get("external_id"),
                    region=onboard_req.cloud_config.get("region", "us-east-1"),
                    aws_account_id=onboard_req.cloud_config.get("aws_account_id", "000000000000"),
                    tenant_id=UUID("00000000-0000-0000-0000-000000000000") # Temp ID
                )
            elif platform == "azure":
                conn = AzureConnection(
                    client_id=onboard_req.cloud_config.get("client_id"),
                    client_secret=onboard_req.cloud_config.get("client_secret"),
                    azure_tenant_id=onboard_req.cloud_config.get("azure_tenant_id"),
                    subscription_id=onboard_req.cloud_config.get("subscription_id"),
                    tenant_id=UUID("00000000-0000-0000-0000-000000000000")
                )
            elif platform == "gcp":
                conn = GCPConnection(
                    project_id=onboard_req.cloud_config.get("project_id"),
                    service_account_json=onboard_req.cloud_config.get("service_account_json"),
                    tenant_id=UUID("00000000-0000-0000-0000-000000000000")
                )
            else:
                raise HTTPException(400, f"Unsupported platform: {platform}")

            if conn:
                adapter = AdapterFactory.get_adapter(conn)
                if not await adapter.verify_connection():
                    raise HTTPException(400, f"Cloud connection verification failed for {platform}. Please check your credentials.")
                logger.info("cloud_connection_verified_successfully", platform=platform)
        
        except HTTPException:
            raise
        except Exception as e:
            logger.error("onboarding_verification_error", platform=platform, error=str(e))
            raise HTTPException(400, f"Error verifying {platform} connection: {str(e)}")
    
    db.add(tenant)
    await db.flush()  # Get tenant.id

    # 3. Create User linked to Tenant
    new_user = User(id=user.id, email=user.email, tenant_id=tenant.id, role=UserRole.OWNER)
    db.add(new_user)
    await db.commit()

    # 4. Audit Log
    audit_log(
        event="tenant_onboarded",
        user_id=str(user.id),
        tenant_id=str(tenant.id),
        details={"tenant_name": onboard_req.tenant_name}
    )

    return OnboardResponse(status="onboarded", tenant_id=tenant.id)
