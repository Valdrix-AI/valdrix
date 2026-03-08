"""Tenant account closure and offboarding controls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus
from app.models.tenant import Tenant, User
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.db.session import get_db

router = APIRouter(tags=["Settings"])

ACCOUNT_CLOSURE_CONFIRMATION = "CLOSE TENANT ACCOUNT"


class AccountClosureRequest(BaseModel):
    confirmation: str = Field(
        ...,
        description=f"Type '{ACCOUNT_CLOSURE_CONFIRMATION}' to confirm tenant closure.",
    )


class AccountClosureResponse(BaseModel):
    status: str
    tenant_id: str
    users_revoked: int
    background_jobs_revoked: int
    identity_revoked: bool
    closed_at: str | None = None


@router.get("/account/status", response_model=AccountClosureResponse)
async def get_account_status(
    current_user: Annotated[CurrentUser, Depends(requires_role("owner"))],
    db: AsyncSession = Depends(get_db),
) -> AccountClosureResponse:
    tenant_id = current_user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")

    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    inactive_users = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(False))
    )
    open_jobs = (
        await db.execute(
            select(BackgroundJob.id).where(
                BackgroundJob.tenant_id == tenant_id,
                BackgroundJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
            )
        )
    ).scalars().all()
    identity = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()
    identity_revoked = identity is None or (
        not bool(identity.scim_enabled)
        and not bool(identity.sso_enabled)
        and not bool(identity.sso_federation_enabled)
        and not bool(identity.scim_bearer_token)
    )

    return AccountClosureResponse(
        status="closed" if tenant.is_deleted else "active",
        tenant_id=str(tenant_id),
        users_revoked=int(inactive_users or 0),
        background_jobs_revoked=len(open_jobs),
        identity_revoked=identity_revoked,
        closed_at=tenant.deleted_at.isoformat() if tenant.deleted_at else None,
    )


@router.post("/account/close", response_model=AccountClosureResponse)
async def close_account(
    payload: AccountClosureRequest,
    current_user: Annotated[CurrentUser, Depends(requires_role("owner"))],
    db: AsyncSession = Depends(get_db),
) -> AccountClosureResponse:
    if payload.confirmation != ACCOUNT_CLOSURE_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirmation text must exactly match "
                f"'{ACCOUNT_CLOSURE_CONFIRMATION}'"
            ),
        )

    tenant_id = current_user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context required")

    tenant = (
        await db.execute(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    identity = (
        await db.execute(
            select(TenantIdentitySettings)
            .where(TenantIdentitySettings.tenant_id == tenant_id)
            .with_for_update(of=TenantIdentitySettings)
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if tenant.is_deleted:
        open_jobs = (
            await db.execute(
                select(BackgroundJob.id).where(
                    BackgroundJob.tenant_id == tenant_id,
                    BackgroundJob.status.in_(
                        [JobStatus.PENDING.value, JobStatus.RUNNING.value]
                    ),
                )
            )
        ).scalars().all()
        return AccountClosureResponse(
            status="already_closed",
            tenant_id=str(tenant_id),
            users_revoked=0,
            background_jobs_revoked=len(open_jobs),
            identity_revoked=identity is None or not bool(identity.scim_bearer_token),
            closed_at=tenant.deleted_at.isoformat() if tenant.deleted_at else now.isoformat(),
        )

    user_update = await db.execute(
        update(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(True))
        .values(is_active=False)
    )
    job_update = await db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
        )
        .values(
            status=JobStatus.FAILED.value,
            error_message="tenant_closed",
            completed_at=now,
            is_deleted=True,
        )
    )

    if identity is not None:
        identity.sso_enabled = False
        identity.allowed_email_domains = []
        identity.sso_federation_enabled = False
        identity.sso_federation_provider_id = None
        identity.scim_enabled = False
        identity.scim_bearer_token = None
        identity.scim_group_mappings = []
        identity.scim_last_rotated_at = now

    tenant.is_deleted = True
    tenant.deleted_at = now

    audit = AuditLogger(db=db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.TENANT_DELETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        resource_type="tenant",
        resource_id=str(tenant_id),
        details={
            "offboarding": {
                "users_revoked": int(user_update.rowcount or 0),
                "background_jobs_revoked": int(job_update.rowcount or 0),
                "identity_revoked": identity is not None,
                "closed_at": now.isoformat(),
            }
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/settings/account/close",
    )

    await db.commit()

    return AccountClosureResponse(
        status="closed",
        tenant_id=str(tenant_id),
        users_revoked=int(user_update.rowcount or 0),
        background_jobs_revoked=int(job_update.rowcount or 0),
        identity_revoked=identity is not None,
        closed_at=now.isoformat(),
    )
