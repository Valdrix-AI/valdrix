"""
Azure and GCP connection endpoints (Growth+).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.schemas.connections import (
    AzureConnectionCreate,
    AzureConnectionResponse,
    GCPConnectionCreate,
    GCPConnectionResponse,
)
from app.modules.governance.api.v1.settings.connections_helpers import (
    _enforce_connection_limit,
    _require_tenant_id,
    check_growth_tier,
)
from app.shared.connections.azure import AzureConnectionService
from app.shared.connections.gcp import GCPConnectionService
from app.shared.connections.oidc import OIDCService
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.logging import audit_log
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db

router = APIRouter()


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
        is_active=False,
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
    check_growth_tier(current_user)
    return await AzureConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/azure", response_model=list[AzureConnectionResponse])
async def list_azure_connections(
    current_user: CurrentUser = Depends(requires_role("member")),
    db: AsyncSession = Depends(get_db),
) -> list[AzureConnection]:
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
        is_active=False,
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
