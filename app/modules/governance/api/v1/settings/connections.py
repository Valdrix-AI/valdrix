"""
Unified Multi-Cloud Connection Router

Handles CRUD operations for AWS, Azure, and GCP connections.
Enforces "Growth Tier" (or higher) requirement for Azure/GCP.
"""

from uuid import UUID
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.shared.db.session import get_db
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.logging import audit_log
from app.shared.core.rate_limit import rate_limit, standard_limit
from app.shared.connections.aws import AWSConnectionService
from app.shared.connections.azure import AzureConnectionService
from app.shared.connections.gcp import GCPConnectionService
from app.shared.connections.organizations import OrganizationsDiscoveryService
from app.shared.connections.instructions import ConnectionInstructionService
from app.shared.core.pricing import PricingTier

# Models
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.tenant import Tenant
from app.models.discovered_account import DiscoveredAccount

# Schemas
from app.schemas.connections import (
    AWSConnectionCreate, AWSConnectionResponse, TemplateResponse,
    AzureConnectionCreate, AzureConnectionResponse,
    GCPConnectionCreate, GCPConnectionResponse,
    DiscoveredAccountResponse
)

logger = structlog.get_logger()
router = APIRouter(tags=["connections"])


# ==================== Helpers ====================

async def check_growth_tier(user: CurrentUser, db: AsyncSession):
    """
    Ensure tenant is on 'growth', 'pro', or 'enterprise' plan.
    Uses cached tenant lookup for performance.
    """
    from app.shared.core.cache import get_cache_service

    cache = get_cache_service()
    cache_key = f"tenant_plan:{user.tenant_id}"

    cached_plan = None
    try:
        cached_plan = await cache.get(cache_key)
    except Exception as e:
        logger.warning("tenant_plan_cache_get_failed", tenant_id=str(user.tenant_id), error=str(e))

    if cached_plan is not None:
        try:
            current_plan = PricingTier(cached_plan)
            return _enforce_growth_tier(current_plan, user)
        except ValueError:
            logger.warning(
                "tenant_plan_cache_invalid",
                tenant_id=str(user.tenant_id),
                cached_plan=cached_plan
            )

    # Fetch from DB and cache
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(404, "Tenant context lost")

    try:
        current_plan = PricingTier(tenant.plan)
    except ValueError:
        current_plan = PricingTier.FREE
    
    # Cache for 1 hour
    try:
        await cache.set(cache_key, tenant.plan, ttl=timedelta(hours=1))
    except Exception as e:
        logger.warning("tenant_plan_cache_set_failed", tenant_id=str(user.tenant_id), error=str(e))

    return _enforce_growth_tier(current_plan, user)
def _enforce_growth_tier(current_plan: PricingTier, user: CurrentUser) -> None:
    allowed_plans = {
        PricingTier.GROWTH,
        PricingTier.PRO,
        PricingTier.ENTERPRISE
    }

    if current_plan not in allowed_plans:
        logger.warning("tier_gate_denied", tenant_id=str(user.tenant_id), plan=current_plan.value, required="growth")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Multi-cloud support requires 'Growth' plan or higher. Current plan: {current_plan.value}"
        )


# ==================== AWS Endpoints ====================

@router.post("/aws/setup", response_model=TemplateResponse)
@rate_limit("10/minute") # Protect setup against scanning
async def get_aws_setup_templates(request: Request):
    """Get CloudFormation/Terraform templates and Magic Link for AWS setup."""
    external_id = AWSConnection.generate_external_id()
    templates = AWSConnectionService.get_setup_templates(external_id)
    return TemplateResponse(**templates)


@router.post("/azure/setup")
async def get_azure_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
):
    """Get Azure Workload Identity setup instructions."""
    return ConnectionInstructionService.get_azure_setup_snippet(str(current_user.tenant_id))


@router.post("/gcp/setup")
async def get_gcp_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
):
    """Get GCP Identity Federation setup instructions."""
    return ConnectionInstructionService.get_gcp_setup_snippet(str(current_user.tenant_id))


@router.post("/aws", response_model=AWSConnectionResponse, status_code=status.HTTP_201_CREATED)
@standard_limit
async def create_aws_connection(
    request: Request,
    data: AWSConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """Register a new AWS connection (Available on all tiers)."""
    # Check duplicate in single optimized query
    existing = await db.scalar(
        select(AWSConnection.id).where(
            AWSConnection.tenant_id == current_user.tenant_id,
            AWSConnection.aws_account_id == data.aws_account_id,
        )
    )
    if existing:
        raise HTTPException(409, f"AWS account {data.aws_account_id} already connected")

    connection = AWSConnection(
        tenant_id=current_user.tenant_id,
        aws_account_id=data.aws_account_id,
        role_arn=data.role_arn,
        external_id=data.external_id,
        region=data.region,
        is_management_account=data.is_management_account,
        organization_id=data.organization_id,
        status="pending",
    )

    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log("aws_connection_created", str(current_user.id), str(current_user.tenant_id),
             {"aws_account_id": data.aws_account_id})

    return connection


@router.get("/aws", response_model=list[AWSConnectionResponse])
async def list_aws_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == current_user.tenant_id))
    return result.scalars().all()


@router.post("/aws/{connection_id}/verify")
@standard_limit
async def verify_aws_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    return await AWSConnectionService(db).verify_connection(connection_id, current_user.tenant_id)


@router.delete("/aws/{connection_id}", status_code=204)
async def delete_aws_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id, 
            AWSConnection.tenant_id == current_user.tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log("aws_connection_deleted", str(current_user.id), str(current_user.tenant_id), {"id": str(connection_id)})


@router.post("/aws/{connection_id}/sync-org")
async def sync_aws_org(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger AWS Organizations account discovery."""
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id,
            AWSConnection.tenant_id == current_user.tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection or not connection.is_management_account:
        raise HTTPException(404, "Management account connection not found")

    count = await OrganizationsDiscoveryService.sync_accounts(db, connection)
    return {"message": f"Successfully discovered {count} accounts", "count": count}


@router.get("/aws/discovered", response_model=list[DiscoveredAccountResponse])
async def list_discovered_accounts(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """List accounts discovered via AWS Organizations."""
    # Find all management connections for this tenant
    res = await db.execute(
        select(AWSConnection.id).where(
            AWSConnection.tenant_id == current_user.tenant_id,
            AWSConnection.is_management_account
        )
    )
    mgmt_ids = [r for r in res.scalars().all()]
    
    if not mgmt_ids:
        return []

    result = await db.execute(
        select(DiscoveredAccount).where(
            DiscoveredAccount.management_connection_id.in_(mgmt_ids)
        ).order_by(DiscoveredAccount.last_discovered_at.desc())
    )
    return result.scalars().all()


@router.post("/aws/discovered/{discovered_id}/link")
async def link_discovered_account(
    discovered_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """Link a discovered account by creating a standard connection."""
    # Double check ownership via management connection in the same query
    stmt = (
        select(DiscoveredAccount, AWSConnection)
        .join(AWSConnection, DiscoveredAccount.management_connection_id == AWSConnection.id)
        .where(
            DiscoveredAccount.id == discovered_id,
            AWSConnection.tenant_id == current_user.tenant_id
        )
    )
    res = await db.execute(stmt)
    row = res.one_or_none()
    if not row:
        raise HTTPException(404, "Discovered account not found or not authorized")
    
    discovered, mgmt = row

    # Create standard connection
    # We use the same External ID or a common role pattern
    # In a real enterprise flow, the user specifies the role name (e.g., 'OrganizationAccountAccessRole')
    role_name = "OrganizationAccountAccessRole" # Default for AWS Orgs
    role_arn = f"arn:aws:iam::{discovered.account_id}:role/{role_name}"
    
    # Check duplicate
    existing = await db.execute(
        select(AWSConnection).where(
            AWSConnection.aws_account_id == discovered.account_id,
            AWSConnection.tenant_id == current_user.tenant_id
        )
    )
    if existing.scalar_one_or_none():
        discovered.status = "linked"
        await db.commit()
        return {"message": "Account already linked", "status": "existing"}

    connection = AWSConnection(
        tenant_id=current_user.tenant_id,
        aws_account_id=discovered.account_id,
        role_arn=role_arn,
        external_id=mgmt.external_id, # Reuse external ID if roles share it
        region="us-east-1",
        status="pending"
    )
    db.add(connection)
    discovered.status = "linked"
    await db.commit()
    
    return {"message": "Account linked successfully", "connection_id": str(connection.id)}


# ==================== Azure Endpoints (Growth+) ====================

@router.post("/azure", response_model=AzureConnectionResponse, status_code=status.HTTP_201_CREATED)
@rate_limit("5/minute")
async def create_azure_connection(
    request: Request,
    data: AzureConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    # Item 7: Hard Tier Gating for Azure
    await check_growth_tier(current_user, db)

    connection = await db.scalar(
        select(AzureConnection).where(
            AzureConnection.tenant_id == current_user.tenant_id,
            AzureConnection.subscription_id == data.subscription_id
        )
    )
    if connection:
        raise HTTPException(409, f"Azure subscription {data.subscription_id} already connected")

    connection = AzureConnection(
        tenant_id=current_user.tenant_id,
        name=data.name,
        azure_tenant_id=data.azure_tenant_id,
        client_id=data.client_id,
        subscription_id=data.subscription_id,
        client_secret=data.client_secret,
        is_active=False # Default to inactive until verified
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log("azure_connection_created", str(current_user.id), str(current_user.tenant_id), 
             {"subscription_id": data.subscription_id})
    return connection


@router.post("/azure/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_azure_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """Verify Azure connection credentials."""
    # Item 7: Ensure verification is also gated
    await check_growth_tier(current_user, db)
    return await AzureConnectionService(db).verify_connection(connection_id, current_user.tenant_id)


@router.get("/azure", response_model=list[AzureConnectionResponse])
async def list_azure_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    # Retrieve regardless of current tier (if they downgraded, they can still see/delete)
    return await AzureConnectionService(db).list_connections(current_user.tenant_id)


@router.delete("/azure/{connection_id}", status_code=204)
async def delete_azure_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AzureConnection).where(
            AzureConnection.id == connection_id,
            AzureConnection.tenant_id == current_user.tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log("azure_connection_deleted", str(current_user.id), str(current_user.tenant_id), {"id": str(connection_id)})


# ==================== GCP Endpoints (Growth+) ====================

@router.post("/gcp", response_model=GCPConnectionResponse, status_code=status.HTTP_201_CREATED)
@rate_limit("5/minute")
async def create_gcp_connection(
    request: Request,
    data: GCPConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_role("member")),
):
    # Item 7: Hard Tier Gating for GCP
    await check_growth_tier(current_user, db)

    connection = await db.scalar(
        select(GCPConnection).where(
            GCPConnection.tenant_id == current_user.tenant_id,
            GCPConnection.project_id == data.project_id
        )
    )
    if connection:
        raise HTTPException(409, f"GCP project {data.project_id} already connected")

    if data.auth_method == "workload_identity":
        from app.shared.connections.oidc import OIDCService

        success, error = await OIDCService.verify_gcp_access(
            project_id=data.project_id,
            tenant_id=str(current_user.tenant_id)
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"GCP Workload Identity verification failed: {error}"
            )

    connection = GCPConnection(
        tenant_id=current_user.tenant_id,
        name=data.name,
        project_id=data.project_id,
        service_account_json=data.service_account_json,
        auth_method=data.auth_method,
        billing_project_id=data.billing_project_id,
        billing_dataset=data.billing_dataset,
        billing_table=data.billing_table,
        is_active=False, # Default to inactive until verified
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log("gcp_connection_created", str(current_user.id), str(current_user.tenant_id), 
             {"project_id": data.project_id})
    return connection


@router.post("/gcp/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_gcp_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    """Verify GCP connection credentials."""
    # Item 7: Guard verification logic
    await check_growth_tier(current_user, db)
    return await GCPConnectionService(db).verify_connection(connection_id, current_user.tenant_id)


@router.get("/gcp", response_model=list[GCPConnectionResponse])
async def list_gcp_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GCPConnection).where(GCPConnection.tenant_id == current_user.tenant_id))
    return result.scalars().all()


@router.delete("/gcp/{connection_id}", status_code=204)
async def delete_gcp_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GCPConnection).where(
            GCPConnection.id == connection_id,
            GCPConnection.tenant_id == current_user.tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log("gcp_connection_deleted", str(current_user.id), str(current_user.tenant_id), {"id": str(connection_id)})
