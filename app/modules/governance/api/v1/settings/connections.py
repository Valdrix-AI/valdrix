"""
Unified Multi-Cloud Connection Router

Handles CRUD operations for AWS, Azure, GCP, and Cloud+ connectors.
Enforces tier requirements for multi-cloud and cloud-plus features.
"""

from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from app.shared.db.session import get_db
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.logging import audit_log
from app.shared.core.rate_limit import rate_limit, standard_limit
from app.shared.connections.aws import AWSConnectionService
from app.shared.connections.azure import AzureConnectionService
from app.shared.connections.gcp import GCPConnectionService
from app.shared.connections.saas import SaaSConnectionService
from app.shared.connections.license import LicenseConnectionService
from app.shared.connections.platform import PlatformConnectionService
from app.shared.connections.hybrid import HybridConnectionService
from app.shared.connections.organizations import OrganizationsDiscoveryService
from app.shared.connections.instructions import ConnectionInstructionService
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    get_tier_limit,
    is_feature_enabled,
    normalize_tier,
)

# Models
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection
from app.models.discovered_account import DiscoveredAccount

# Schemas
from app.schemas.connections import (
    AWSConnectionCreate,
    AWSConnectionResponse,
    TemplateResponse,
    AzureConnectionCreate,
    AzureConnectionResponse,
    GCPConnectionCreate,
    GCPConnectionResponse,
    SaaSConnectionCreate,
    SaaSConnectionResponse,
    LicenseConnectionCreate,
    LicenseConnectionResponse,
    PlatformConnectionCreate,
    PlatformConnectionResponse,
    HybridConnectionCreate,
    HybridConnectionResponse,
    DiscoveredAccountResponse,
)

logger = structlog.get_logger()
router = APIRouter(tags=["connections"])


# ==================== Helpers ====================


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=404, detail="Tenant context lost")
    return user.tenant_id


def check_growth_tier(user: CurrentUser) -> PricingTier:
    """
    Ensure tenant is on 'growth', 'pro', or 'enterprise' plan.

    We rely on `CurrentUser.tier` (DB-backed per request via `get_current_user`) instead of
    an additional cache + DB lookup. This avoids staleness bugs after upgrades.
    """
    current_plan = normalize_tier(getattr(user, "tier", PricingTier.FREE_TRIAL))
    _enforce_growth_tier(current_plan, user)
    return current_plan


def check_cloud_plus_tier(user: CurrentUser) -> PricingTier:
    """
    Ensure Cloud+ connectors are available for the tenant tier.
    """
    current_plan = normalize_tier(getattr(user, "tier", PricingTier.FREE_TRIAL))
    if is_feature_enabled(current_plan, FeatureFlag.CLOUD_PLUS_CONNECTORS):
        return current_plan

    logger.warning(
        "tier_gate_denied_cloud_plus",
        tenant_id=str(user.tenant_id),
        plan=current_plan.value,
        required_feature=FeatureFlag.CLOUD_PLUS_CONNECTORS.value,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Cloud+ connectors require 'Pro' plan or higher. Current plan: {current_plan.value}",
    )


async def _enforce_connection_limit(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    plan: PricingTier,
    limit_key: str,
    model: Any,
    label: str,
) -> None:
    """Enforce plan limits for connection creation."""
    limit_value = get_tier_limit(plan, limit_key)
    if limit_value is None:
        return

    try:
        max_allowed = int(limit_value)
    except (TypeError, ValueError):
        logger.warning(
            "tier_limit_invalid",
            plan=plan.value,
            limit_key=limit_key,
            limit_value=limit_value,
        )
        return

    if max_allowed <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{label} connections are not available on plan '{plan.value}'. Please upgrade.",
        )

    used = await db.scalar(
        select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
    )
    used_count = int(used or 0)
    if used_count >= max_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Plan limit reached for {label} connections: {used_count}/{max_allowed}. "
                "Please upgrade to add more."
            ),
        )


def _enforce_growth_tier(current_plan: PricingTier, user: CurrentUser) -> None:
    allowed_plans = {PricingTier.GROWTH, PricingTier.PRO, PricingTier.ENTERPRISE}

    if current_plan not in allowed_plans:
        logger.warning(
            "tier_gate_denied",
            tenant_id=str(user.tenant_id),
            plan=current_plan.value,
            required="growth",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Multi-cloud support requires 'Growth' plan or higher. Current plan: {current_plan.value}",
        )


# ==================== AWS Endpoints ====================


@router.post("/aws/setup", response_model=TemplateResponse)
@rate_limit("10/minute")  # Protect setup against scanning
async def get_aws_setup_templates(request: Request) -> TemplateResponse:
    """Get CloudFormation/Terraform templates and Magic Link for AWS setup."""
    external_id = AWSConnection.generate_external_id()
    templates = AWSConnectionService.get_setup_templates(external_id)
    return TemplateResponse(**templates)


@router.post("/azure/setup")
async def get_azure_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, str]:
    """Get Azure Workload Identity setup instructions."""
    return ConnectionInstructionService.get_azure_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/gcp/setup")
async def get_gcp_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, str]:
    """Get GCP Identity Federation setup instructions."""
    return ConnectionInstructionService.get_gcp_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/saas/setup")
async def get_saas_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, Any]:
    """Get SaaS Cloud+ setup instructions."""
    return ConnectionInstructionService.get_saas_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/license/setup")
async def get_license_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, Any]:
    """Get License/ITAM Cloud+ setup instructions."""
    return ConnectionInstructionService.get_license_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/platform/setup")
async def get_platform_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, Any]:
    """Get internal platform Cloud+ setup instructions."""
    return ConnectionInstructionService.get_platform_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/hybrid/setup")
async def get_hybrid_setup(
    current_user: CurrentUser = Depends(requires_role("member")),
) -> dict[str, Any]:
    """Get private/hybrid infra Cloud+ setup instructions."""
    return ConnectionInstructionService.get_hybrid_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post(
    "/aws", response_model=AWSConnectionResponse, status_code=status.HTTP_201_CREATED
)
@standard_limit
async def create_aws_connection(
    request: Request,
    data: AWSConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> AWSConnection:
    tenant_id = _require_tenant_id(current_user)
    # Register a new AWS connection (available on all tiers).
    # Check duplicate in single optimized query
    existing = await db.scalar(
        select(AWSConnection.id).where(
            AWSConnection.tenant_id == tenant_id,
            AWSConnection.aws_account_id == data.aws_account_id,
        )
    )
    if existing:
        raise HTTPException(409, f"AWS account {data.aws_account_id} already connected")

    plan = normalize_tier(getattr(current_user, "tier", PricingTier.FREE_TRIAL))
    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_aws_accounts",
        model=AWSConnection,
        label="AWS account",
    )

    connection = AWSConnection(
        tenant_id=tenant_id,
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

    audit_log(
        "aws_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"aws_account_id": data.aws_account_id},
    )

    return connection


@router.get("/aws", response_model=list[AWSConnectionResponse])
async def list_aws_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[AWSConnection]:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


@router.post("/aws/{connection_id}/verify")
@standard_limit
async def verify_aws_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await AWSConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.delete("/aws/{connection_id}", status_code=204)
async def delete_aws_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id, AWSConnection.tenant_id == tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "aws_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


@router.post("/aws/{connection_id}/sync-org")
async def sync_aws_org(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant_id = _require_tenant_id(current_user)
    """Trigger AWS Organizations account discovery."""
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id, AWSConnection.tenant_id == tenant_id
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
) -> list[DiscoveredAccount]:
    tenant_id = _require_tenant_id(current_user)
    """List accounts discovered via AWS Organizations."""
    # Find all management connections for this tenant
    res = await db.execute(
        select(AWSConnection.id).where(
            AWSConnection.tenant_id == tenant_id, AWSConnection.is_management_account
        )
    )
    mgmt_ids = [r for r in res.scalars().all()]

    if not mgmt_ids:
        return []

    result = await db.execute(
        select(DiscoveredAccount)
        .where(DiscoveredAccount.management_connection_id.in_(mgmt_ids))
        .order_by(DiscoveredAccount.last_discovered_at.desc())
    )
    return list(result.scalars().all())


@router.post("/aws/discovered/{discovered_id}/link")
async def link_discovered_account(
    discovered_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant_id = _require_tenant_id(current_user)
    plan = normalize_tier(getattr(current_user, "tier", PricingTier.FREE_TRIAL))
    """Link a discovered account by creating a standard connection."""
    # Double check ownership via management connection in the same query
    stmt = (
        select(DiscoveredAccount, AWSConnection)
        .join(
            AWSConnection,
            DiscoveredAccount.management_connection_id == AWSConnection.id,
        )
        .where(
            DiscoveredAccount.id == discovered_id, AWSConnection.tenant_id == tenant_id
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
    role_name = "OrganizationAccountAccessRole"  # Default for AWS Orgs
    role_arn = f"arn:aws:iam::{discovered.account_id}:role/{role_name}"

    # Check duplicate
    existing = await db.execute(
        select(AWSConnection).where(
            AWSConnection.aws_account_id == discovered.account_id,
            AWSConnection.tenant_id == tenant_id,
        )
    )
    if existing.scalar_one_or_none():
        discovered.status = "linked"
        await db.commit()
        return {"message": "Account already linked", "status": "existing"}

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_aws_accounts",
        model=AWSConnection,
        label="AWS account",
    )

    connection = AWSConnection(
        tenant_id=tenant_id,
        aws_account_id=discovered.account_id,
        role_arn=role_arn,
        external_id=mgmt.external_id,  # Reuse external ID if roles share it
        region="us-east-1",
        status="pending",
    )
    db.add(connection)
    discovered.status = "linked"
    await db.commit()

    return {
        "message": "Account linked successfully",
        "connection_id": str(connection.id),
    }


# ==================== Azure Endpoints (Growth+) ====================


@router.post(
    "/azure",
    response_model=AzureConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_azure_connection(
    request: Request,
    data: AzureConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> AzureConnection:
    tenant_id = _require_tenant_id(current_user)

    # Item 7: Hard Tier Gating for Azure
    plan = check_growth_tier(current_user)

    connection = await db.scalar(
        select(AzureConnection).where(
            AzureConnection.tenant_id == tenant_id,
            AzureConnection.subscription_id == data.subscription_id,
        )
    )
    if connection:
        raise HTTPException(
            409, f"Azure subscription {data.subscription_id} already connected"
        )

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_azure_tenants",
        model=AzureConnection,
        label="Azure subscription",
    )

    connection = AzureConnection(
        tenant_id=tenant_id,
        name=data.name,
        azure_tenant_id=data.azure_tenant_id,
        client_id=data.client_id,
        subscription_id=data.subscription_id,
        client_secret=data.client_secret,
        is_active=False,  # Default to inactive until verified
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "azure_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"subscription_id": data.subscription_id},
    )
    return connection


@router.post("/azure/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_azure_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verify Azure connection credentials."""
    # Item 7: Ensure verification is also gated
    check_growth_tier(current_user)
    return await AzureConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/azure", response_model=list[AzureConnectionResponse])
async def list_azure_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[AzureConnection]:
    # Retrieve regardless of current tier (if they downgraded, they can still see/delete)
    return await AzureConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/azure/{connection_id}", status_code=204)
async def delete_azure_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(AzureConnection).where(
            AzureConnection.id == connection_id, AzureConnection.tenant_id == tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "azure_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


# ==================== GCP Endpoints (Growth+) ====================


@router.post(
    "/gcp", response_model=GCPConnectionResponse, status_code=status.HTTP_201_CREATED
)
@rate_limit("5/minute")
async def create_gcp_connection(
    request: Request,
    data: GCPConnectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_role("member")),
) -> GCPConnection:
    tenant_id = _require_tenant_id(current_user)
    # Item 7: Hard Tier Gating for GCP
    plan = check_growth_tier(current_user)

    connection = await db.scalar(
        select(GCPConnection).where(
            GCPConnection.tenant_id == tenant_id,
            GCPConnection.project_id == data.project_id,
        )
    )
    if connection:
        raise HTTPException(409, f"GCP project {data.project_id} already connected")

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_gcp_projects",
        model=GCPConnection,
        label="GCP project",
    )

    if data.auth_method == "workload_identity":
        from app.shared.connections.oidc import OIDCService

        success, error = await OIDCService.verify_gcp_access(
            project_id=data.project_id,
            tenant_id=str(tenant_id),
        )
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"GCP Workload Identity verification failed: {error}",
            )

    connection = GCPConnection(
        tenant_id=tenant_id,
        name=data.name,
        project_id=data.project_id,
        service_account_json=data.service_account_json,
        auth_method=data.auth_method,
        billing_project_id=data.billing_project_id,
        billing_dataset=data.billing_dataset,
        billing_table=data.billing_table,
        is_active=False,  # Default to inactive until verified
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "gcp_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"project_id": data.project_id},
    )
    return connection


@router.post("/gcp/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_gcp_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Verify GCP connection credentials."""
    # Item 7: Guard verification logic
    check_growth_tier(current_user)
    return await GCPConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/gcp", response_model=list[GCPConnectionResponse])
async def list_gcp_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[GCPConnection]:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(GCPConnection).where(GCPConnection.tenant_id == tenant_id)
    )
    return list(result.scalars().all())


@router.delete("/gcp/{connection_id}", status_code=204)
async def delete_gcp_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(GCPConnection).where(
            GCPConnection.id == connection_id, GCPConnection.tenant_id == tenant_id
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "gcp_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


# ==================== Cloud+ SaaS Endpoints (Pro+) ====================


@router.post(
    "/saas", response_model=SaaSConnectionResponse, status_code=status.HTTP_201_CREATED
)
@rate_limit("5/minute")
async def create_saas_connection(
    request: Request,
    data: SaaSConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> SaaSConnection:
    tenant_id = _require_tenant_id(current_user)
    plan = check_cloud_plus_tier(current_user)

    existing = await db.scalar(
        select(SaaSConnection.id).where(
            SaaSConnection.tenant_id == tenant_id,
            SaaSConnection.vendor == data.vendor,
            SaaSConnection.name == data.name,
        )
    )
    if existing:
        raise HTTPException(
            409, f"SaaS connection '{data.vendor}:{data.name}' already exists"
        )

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_saas_connections",
        model=SaaSConnection,
        label="SaaS",
    )

    connection = SaaSConnection(
        tenant_id=tenant_id,
        name=data.name,
        vendor=data.vendor,
        auth_method=data.auth_method,
        api_key=data.api_key,
        connector_config=data.connector_config,
        spend_feed=data.spend_feed,
        is_active=False,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "saas_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"vendor": data.vendor, "name": data.name},
    )
    return connection


@router.post("/saas/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_saas_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await SaaSConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/saas", response_model=list[SaaSConnectionResponse])
async def list_saas_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[SaaSConnection]:
    return await SaaSConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/saas/{connection_id}", status_code=204)
async def delete_saas_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(SaaSConnection).where(
            SaaSConnection.id == connection_id,
            SaaSConnection.tenant_id == tenant_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "saas_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


# ==================== Cloud+ License Endpoints (Pro+) ====================


@router.post(
    "/license",
    response_model=LicenseConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_license_connection(
    request: Request,
    data: LicenseConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> LicenseConnection:
    tenant_id = _require_tenant_id(current_user)
    plan = check_cloud_plus_tier(current_user)

    existing = await db.scalar(
        select(LicenseConnection.id).where(
            LicenseConnection.tenant_id == tenant_id,
            LicenseConnection.vendor == data.vendor,
            LicenseConnection.name == data.name,
        )
    )
    if existing:
        raise HTTPException(
            409, f"License connection '{data.vendor}:{data.name}' already exists"
        )

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_license_connections",
        model=LicenseConnection,
        label="License",
    )

    connection = LicenseConnection(
        tenant_id=tenant_id,
        name=data.name,
        vendor=data.vendor,
        auth_method=data.auth_method,
        api_key=data.api_key,
        connector_config=data.connector_config,
        license_feed=data.license_feed,
        is_active=False,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "license_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"vendor": data.vendor, "name": data.name},
    )
    return connection


@router.post("/license/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_license_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await LicenseConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/license", response_model=list[LicenseConnectionResponse])
async def list_license_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[LicenseConnection]:
    return await LicenseConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/license/{connection_id}", status_code=204)
async def delete_license_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(LicenseConnection).where(
            LicenseConnection.id == connection_id,
            LicenseConnection.tenant_id == tenant_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "license_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


# ==================== Cloud+ Platform Endpoints (Pro+) ====================


@router.post(
    "/platform",
    response_model=PlatformConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_platform_connection(
    request: Request,
    data: PlatformConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> PlatformConnection:
    tenant_id = _require_tenant_id(current_user)
    plan = check_cloud_plus_tier(current_user)

    existing = await db.scalar(
        select(PlatformConnection.id).where(
            PlatformConnection.tenant_id == tenant_id,
            PlatformConnection.vendor == data.vendor,
            PlatformConnection.name == data.name,
        )
    )
    if existing:
        raise HTTPException(
            409, f"Platform connection '{data.vendor}:{data.name}' already exists"
        )

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_platform_connections",
        model=PlatformConnection,
        label="Platform",
    )

    connection = PlatformConnection(
        tenant_id=tenant_id,
        name=data.name,
        vendor=data.vendor,
        auth_method=data.auth_method,
        api_key=data.api_key,
        api_secret=data.api_secret,
        connector_config=data.connector_config,
        spend_feed=data.spend_feed,
        is_active=False,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "platform_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"vendor": data.vendor, "name": data.name},
    )
    return connection


@router.post("/platform/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_platform_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await PlatformConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/platform", response_model=list[PlatformConnectionResponse])
async def list_platform_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[PlatformConnection]:
    return await PlatformConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/platform/{connection_id}", status_code=204)
async def delete_platform_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.id == connection_id,
            PlatformConnection.tenant_id == tenant_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "platform_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )


# ==================== Cloud+ Hybrid Endpoints (Pro+) ====================


@router.post(
    "/hybrid",
    response_model=HybridConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_hybrid_connection(
    request: Request,
    data: HybridConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> HybridConnection:
    tenant_id = _require_tenant_id(current_user)
    plan = check_cloud_plus_tier(current_user)

    existing = await db.scalar(
        select(HybridConnection.id).where(
            HybridConnection.tenant_id == tenant_id,
            HybridConnection.vendor == data.vendor,
            HybridConnection.name == data.name,
        )
    )
    if existing:
        raise HTTPException(
            409, f"Hybrid connection '{data.vendor}:{data.name}' already exists"
        )

    await _enforce_connection_limit(
        db=db,
        tenant_id=tenant_id,
        plan=plan,
        limit_key="max_hybrid_connections",
        model=HybridConnection,
        label="Hybrid",
    )

    connection = HybridConnection(
        tenant_id=tenant_id,
        name=data.name,
        vendor=data.vendor,
        auth_method=data.auth_method,
        api_key=data.api_key,
        api_secret=data.api_secret,
        connector_config=data.connector_config,
        spend_feed=data.spend_feed,
        is_active=False,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)

    audit_log(
        "hybrid_connection_created",
        str(current_user.id),
        str(current_user.tenant_id),
        {"vendor": data.vendor, "name": data.name},
    )
    return connection


@router.post("/hybrid/{connection_id}/verify")
@rate_limit("10/minute")
async def verify_hybrid_connection(
    request: Request,
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await HybridConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/hybrid", response_model=list[HybridConnectionResponse])
async def list_hybrid_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[HybridConnection]:
    return await HybridConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/hybrid/{connection_id}", status_code=204)
async def delete_hybrid_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> None:
    tenant_id = _require_tenant_id(current_user)
    result = await db.execute(
        select(HybridConnection).where(
            HybridConnection.id == connection_id,
            HybridConnection.tenant_id == tenant_id,
        )
    )
    connection = result.scalar_one_or_none()
    if not connection:
        raise HTTPException(404, "Connection not found")

    await db.delete(connection)
    await db.commit()
    audit_log(
        "hybrid_connection_deleted",
        str(current_user.id),
        str(current_user.tenant_id),
        {"id": str(connection_id)},
    )
