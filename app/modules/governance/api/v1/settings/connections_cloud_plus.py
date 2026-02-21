"""
Cloud+ connector endpoints (Pro+): SaaS, License, Platform, Hybrid.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hybrid_connection import HybridConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.saas_connection import SaaSConnection
from app.schemas.connections import (
    HybridConnectionCreate,
    HybridConnectionResponse,
    LicenseConnectionCreate,
    LicenseConnectionResponse,
    PlatformConnectionCreate,
    PlatformConnectionResponse,
    SaaSConnectionCreate,
    SaaSConnectionResponse,
)
from app.modules.governance.api.v1.settings.connections_helpers import (
    _enforce_connection_limit,
    _require_tenant_id,
    check_cloud_plus_tier,
)
from app.shared.connections.hybrid import HybridConnectionService
from app.shared.connections.license import LicenseConnectionService
from app.shared.connections.platform import PlatformConnectionService
from app.shared.connections.saas import SaaSConnectionService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.logging import audit_log
from app.shared.core.rate_limit import rate_limit
from app.shared.db.session import get_db

router = APIRouter()


@router.post(
    "/saas", response_model=SaaSConnectionResponse, status_code=status.HTTP_201_CREATED
)
@rate_limit("5/minute")
async def create_saas_connection(
    request: Request,
    data: SaaSConnectionCreate,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await SaaSConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/saas", response_model=list[SaaSConnectionResponse])
async def list_saas_connections(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[SaaSConnection]:
    return await SaaSConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/saas/{connection_id}", status_code=204)
async def delete_saas_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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


@router.post(
    "/license",
    response_model=LicenseConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_license_connection(
    request: Request,
    data: LicenseConnectionCreate,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await LicenseConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/license", response_model=list[LicenseConnectionResponse])
async def list_license_connections(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[LicenseConnection]:
    return await LicenseConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/license/{connection_id}", status_code=204)
async def delete_license_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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


@router.post(
    "/platform",
    response_model=PlatformConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_platform_connection(
    request: Request,
    data: PlatformConnectionCreate,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await PlatformConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/platform", response_model=list[PlatformConnectionResponse])
async def list_platform_connections(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[PlatformConnection]:
    return await PlatformConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/platform/{connection_id}", status_code=204)
async def delete_platform_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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


@router.post(
    "/hybrid",
    response_model=HybridConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
@rate_limit("5/minute")
async def create_hybrid_connection(
    request: Request,
    data: HybridConnectionCreate,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    check_cloud_plus_tier(current_user)
    return await HybridConnectionService(db).verify_connection(
        connection_id, _require_tenant_id(current_user)
    )


@router.get("/hybrid", response_model=list[HybridConnectionResponse])
async def list_hybrid_connections(
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
    db: AsyncSession = Depends(get_db),
) -> list[HybridConnection]:
    return await HybridConnectionService(db).list_connections(
        _require_tenant_id(current_user)
    )


@router.delete("/hybrid/{connection_id}", status_code=204)
async def delete_hybrid_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(requires_role_with_db_context("member")),
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
