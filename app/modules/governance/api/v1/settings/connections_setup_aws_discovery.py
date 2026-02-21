"""
Setup, AWS, and Discovery Wizard endpoints for unified connections.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount
from app.models.discovery_candidate import DiscoveryCandidate
from app.schemas.connections import (
    AWSConnectionCreate,
    AWSConnectionResponse,
    DiscoveredAccountResponse,
    DiscoveryCandidateResponse,
    DiscoveryDeepScanRequest,
    DiscoveryStageARequest,
    DiscoveryStageResponse,
    TemplateResponse,
)
from app.shared.connections.aws import AWSConnectionService
from app.shared.connections.discovery import DiscoveryWizardService
from app.shared.connections.instructions import ConnectionInstructionService
from app.shared.connections.organizations import OrganizationsDiscoveryService
from app.modules.governance.api.v1.settings.connections_helpers import (
    _enforce_connection_limit,
    _require_tenant_id,
    check_idp_deep_scan_tier,
)
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.logging import audit_log
from app.shared.core.pricing import PricingTier, normalize_tier
from app.shared.core.rate_limit import rate_limit, standard_limit
from app.shared.db.session import get_db

router = APIRouter()


@router.post("/aws/setup", response_model=TemplateResponse)
@rate_limit("10/minute")
async def get_aws_setup_templates(request: Request) -> TemplateResponse:
    """Get CloudFormation/Terraform templates and Magic Link for AWS setup."""
    external_id = AWSConnection.generate_external_id()
    templates = AWSConnectionService.get_setup_templates(external_id)
    return TemplateResponse(**templates)


@router.post("/azure/setup")
async def get_azure_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
) -> dict[str, str]:
    """Get Azure Workload Identity setup instructions."""
    return ConnectionInstructionService.get_azure_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/gcp/setup")
async def get_gcp_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
) -> dict[str, str]:
    """Get GCP Identity Federation setup instructions."""
    return ConnectionInstructionService.get_gcp_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/saas/setup")
async def get_saas_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
) -> dict[str, Any]:
    """Get SaaS Cloud+ setup instructions."""
    return ConnectionInstructionService.get_saas_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/license/setup")
async def get_license_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
) -> dict[str, Any]:
    """Get License/ITAM Cloud+ setup instructions."""
    return ConnectionInstructionService.get_license_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/platform/setup")
async def get_platform_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
) -> dict[str, Any]:
    """Get internal platform Cloud+ setup instructions."""
    return ConnectionInstructionService.get_platform_setup_snippet(
        str(_require_tenant_id(current_user))
    )


@router.post("/hybrid/setup")
async def get_hybrid_setup(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> AWSConnection:
    tenant_id = _require_tenant_id(current_user)

    existing = await db.scalar(
        select(AWSConnection.id).where(
            AWSConnection.tenant_id == tenant_id,
            AWSConnection.aws_account_id == data.aws_account_id,
        )
    )
    if existing:
        raise HTTPException(409, f"AWS account {data.aws_account_id} already connected")

    plan = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await AWSConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.delete("/aws/{connection_id}", status_code=204)
async def delete_aws_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant_id = _require_tenant_id(current_user)
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[DiscoveredAccount]:
    tenant_id = _require_tenant_id(current_user)

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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant_id = _require_tenant_id(current_user)
    plan = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

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
    role_name = "OrganizationAccountAccessRole"
    role_arn = f"arn:aws:iam::{discovered.account_id}:role/{role_name}"

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
        external_id=mgmt.external_id,
        # Keep discovered member accounts provider-neutral by default so
        # downstream AWS scans can perform multi-region discovery.
        region="global",
        status="pending",
    )
    db.add(connection)
    discovered.status = "linked"
    await db.commit()

    return {
        "message": "Account linked successfully",
        "connection_id": str(connection.id),
    }


@router.post("/discovery/stage-a", response_model=DiscoveryStageResponse)
@rate_limit("20/minute")
async def discovery_stage_a(
    request: Request,
    data: DiscoveryStageARequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryStageResponse:
    tenant_id = _require_tenant_id(current_user)
    service = DiscoveryWizardService(db)
    try:
        domain, candidates, warnings = await service.discover_stage_a(
            tenant_id=tenant_id,
            email=str(data.email),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit_log(
        "discovery_stage_a_completed",
        str(current_user.id),
        str(tenant_id),
        {
            "domain": domain,
            "candidate_count": len(candidates),
        },
    )
    return DiscoveryStageResponse(
        domain=domain,
        candidates=[DiscoveryCandidateResponse.model_validate(c) for c in candidates],
        warnings=warnings,
        total_candidates=len(candidates),
    )


@router.post("/discovery/deep-scan", response_model=DiscoveryStageResponse)
@rate_limit("10/minute")
async def discovery_deep_scan(
    request: Request,
    data: DiscoveryDeepScanRequest,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryStageResponse:
    tenant_id = _require_tenant_id(current_user)
    check_idp_deep_scan_tier(current_user)

    service = DiscoveryWizardService(db)
    try:
        domain, candidates, warnings = await service.deep_scan_idp(
            tenant_id=tenant_id,
            domain=data.domain,
            idp_provider=data.idp_provider,
            max_users=data.max_users,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit_log(
        "discovery_stage_b_completed",
        str(current_user.id),
        str(tenant_id),
        {
            "domain": domain,
            "idp_provider": data.idp_provider,
            "candidate_count": len(candidates),
        },
    )
    return DiscoveryStageResponse(
        domain=domain,
        candidates=[DiscoveryCandidateResponse.model_validate(c) for c in candidates],
        warnings=warnings,
        total_candidates=len(candidates),
    )


@router.get("/discovery/candidates", response_model=list[DiscoveryCandidateResponse])
async def list_discovery_candidates(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="Optional status filter: pending, accepted, ignored, connected",
    ),
) -> list[DiscoveryCandidate]:
    tenant_id = _require_tenant_id(current_user)
    service = DiscoveryWizardService(db)
    try:
        return await service.list_candidates(tenant_id, status=status_filter)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


async def _update_discovery_candidate_status(
    *,
    current_user: CurrentUser,
    db: AsyncSession,
    candidate_id: UUID,
    next_status: str,
    audit_event: str,
) -> DiscoveryCandidate:
    tenant_id = _require_tenant_id(current_user)
    service = DiscoveryWizardService(db)
    try:
        candidate = await service.update_candidate_status(
            tenant_id, candidate_id, next_status
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    audit_log(
        audit_event,
        str(current_user.id),
        str(tenant_id),
        {
            "candidate_id": str(candidate_id),
            "provider": candidate.provider,
            "category": candidate.category,
        },
    )
    return candidate


@router.post(
    "/discovery/candidates/{candidate_id}/accept",
    response_model=DiscoveryCandidateResponse,
)
@standard_limit
async def accept_discovery_candidate(
    request: Request,
    candidate_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryCandidate:
    return await _update_discovery_candidate_status(
        current_user=current_user,
        db=db,
        candidate_id=candidate_id,
        next_status="accepted",
        audit_event="discovery_candidate_accepted",
    )


@router.post(
    "/discovery/candidates/{candidate_id}/ignore",
    response_model=DiscoveryCandidateResponse,
)
@standard_limit
async def ignore_discovery_candidate(
    request: Request,
    candidate_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryCandidate:
    return await _update_discovery_candidate_status(
        current_user=current_user,
        db=db,
        candidate_id=candidate_id,
        next_status="ignored",
        audit_event="discovery_candidate_ignored",
    )


@router.post(
    "/discovery/candidates/{candidate_id}/connected",
    response_model=DiscoveryCandidateResponse,
)
@standard_limit
async def mark_discovery_candidate_connected(
    request: Request,
    candidate_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> DiscoveryCandidate:
    return await _update_discovery_candidate_status(
        current_user=current_user,
        db=db,
        candidate_id=candidate_id,
        next_status="connected",
        audit_event="discovery_candidate_connected",
    )
