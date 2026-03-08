from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.tenant import Tenant, User, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.domain.security.audit_log import AuditLog
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_close_account_revokes_users_jobs_and_identity(async_client, db, app):
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()

    db.add(Tenant(id=tenant_id, name="Closure Tenant", plan="enterprise"))
    db.add(
        User(
            id=owner_id,
            tenant_id=tenant_id,
            email="owner@valdrics.io",
            role=UserRole.OWNER.value,
            is_active=True,
        )
    )
    db.add(
        User(
            id=member_id,
            tenant_id=tenant_id,
            email="member@valdrics.io",
            role=UserRole.MEMBER.value,
            is_active=True,
        )
    )
    db.add(
        TenantIdentitySettings(
            tenant_id=tenant_id,
            sso_enabled=True,
            allowed_email_domains=["example.com"],
            sso_federation_enabled=True,
            sso_federation_provider_id="provider-id",
            scim_enabled=True,
            scim_bearer_token="secret-token",
            scim_group_mappings=[{"group": "admins", "role": "admin"}],
        )
    )
    db.add(
        BackgroundJob(
            job_type=JobType.COST_INGESTION.value,
            tenant_id=tenant_id,
            status=JobStatus.PENDING.value,
            scheduled_for=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    mock_user = CurrentUser(
        id=owner_id,
        tenant_id=tenant_id,
        email="owner@valdrics.io",
        role=UserRole.OWNER,
        tier=PricingTier.ENTERPRISE,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post(
            "/api/v1/settings/account/close",
            json={"confirmation": "CLOSE TENANT ACCOUNT"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "closed"
        assert payload["users_revoked"] == 2
        assert payload["background_jobs_revoked"] == 1
        assert payload["identity_revoked"] is True

        tenant = (
            await db.execute(select(Tenant).where(Tenant.id == tenant_id))
        ).scalar_one()
        assert tenant.is_deleted is True
        assert tenant.deleted_at is not None

        users = (
            await db.execute(select(User.is_active).where(User.tenant_id == tenant_id))
        ).scalars().all()
        assert users == [False, False]

        identity = (
            await db.execute(
                select(TenantIdentitySettings).where(
                    TenantIdentitySettings.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        assert identity.sso_enabled is False
        assert identity.scim_enabled is False
        assert identity.scim_bearer_token is None
        assert identity.scim_group_mappings == []

        job = (
            await db.execute(
                select(BackgroundJob).where(BackgroundJob.tenant_id == tenant_id)
            )
        ).scalar_one()
        assert job.status == JobStatus.FAILED.value
        assert job.error_message == "tenant_closed"
        assert job.is_deleted is True

        audit = (
            await db.execute(
                select(AuditLog.event_type, AuditLog.resource_type)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.event_timestamp.desc())
                .limit(1)
            )
        ).first()
        assert audit is not None
        assert audit[0] == "tenant.deleted"
        assert audit[1] == "tenant"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_account_is_idempotent(async_client, db, app):
    tenant_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    db.add(
        Tenant(
            id=tenant_id,
            name="Already Closed Tenant",
            plan="enterprise",
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        User(
            id=owner_id,
            tenant_id=tenant_id,
            email="owner-closed@valdrics.io",
            role=UserRole.OWNER.value,
            is_active=False,
        )
    )
    await db.commit()

    mock_user = CurrentUser(
        id=owner_id,
        tenant_id=tenant_id,
        email="owner-closed@valdrics.io",
        role=UserRole.OWNER,
        tier=PricingTier.ENTERPRISE,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post(
            "/api/v1/settings/account/close",
            json={"confirmation": "CLOSE TENANT ACCOUNT"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "already_closed"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
