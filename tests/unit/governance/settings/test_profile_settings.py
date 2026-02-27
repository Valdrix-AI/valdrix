import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.tenant import UserRole, Tenant, User, UserPersona
from app.modules.governance.domain.security.audit_log import AuditLog
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_get_profile_returns_persona(async_client: AsyncClient, app):
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="persona@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
        persona=UserPersona.PLATFORM,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/profile")
        assert response.status_code == 200
        payload = response.json()
        assert payload["email"] == "persona@valdrix.io"
        assert payload["persona"] == "platform"
        assert payload["role"] == "admin"
        assert payload["tier"] == "pro"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile_updates_persona(async_client: AsyncClient, db, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    db.add(Tenant(id=tenant_id, name="Persona Tenant", plan="pro"))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email="persona-update@valdrix.io",
            role=UserRole.ADMIN.value,
            persona=UserPersona.ENGINEERING.value,
            is_active=True,
        )
    )
    await db.commit()

    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="persona-update@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
        persona=UserPersona.ENGINEERING,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile", json={"persona": "finance"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["persona"] == "finance"

        updated = (
            await db.execute(
                select(User.persona).where(
                    User.id == user_id, User.tenant_id == tenant_id
                )
            )
        ).scalar_one()
        assert updated == "finance"

        audit_row = (
            await db.execute(
                select(AuditLog.event_type, AuditLog.details)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.event_timestamp.desc())
                .limit(1)
            )
        ).first()
        assert audit_row is not None
        event_type, details = audit_row
        assert event_type == "settings.updated"
        assert isinstance(details, dict)
        assert details.get("setting") == "persona"
        assert details.get("new") == "finance"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile_rejects_invalid_persona(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="persona-invalid@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile", json={"persona": "unknown"}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile_requires_tenant_context(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=None,
        email="persona-no-tenant@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
        persona=UserPersona.ENGINEERING,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile", json={"persona": "finance"}
        )
        assert response.status_code == 403
        assert "tenant context required" in str(response.json()).lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile_user_not_found(async_client: AsyncClient, db, app):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="Persona Missing User", plan="pro"))
    await db.commit()

    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="persona-missing@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
        persona=UserPersona.PLATFORM,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile", json={"persona": "finance"}
        )
        assert response.status_code == 404
        assert "user not found" in str(response.json()).lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_profile_audit_uses_forwarded_ip(async_client: AsyncClient, db, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    db.add(Tenant(id=tenant_id, name="Persona Tenant Forwarded", plan="pro"))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email="persona-ip@valdrix.io",
            role=UserRole.ADMIN.value,
            persona=UserPersona.ENGINEERING.value,
            is_active=True,
        )
    )
    await db.commit()

    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="persona-ip@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
        persona=UserPersona.ENGINEERING,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile",
            json={"persona": "finance"},
            headers={"X-Forwarded-For": "198.51.100.10, 203.0.113.9"},
        )
        assert response.status_code == 200

        audit_row = (
            await db.execute(
                select(AuditLog.actor_ip)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.event_timestamp.desc())
                .limit(1)
            )
        ).scalar_one()
        assert audit_row == "198.51.100.10"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
