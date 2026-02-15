import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.tenant import Tenant, User, UserPersona
from app.modules.governance.domain.security.audit_log import AuditLog
from app.shared.core.auth import CurrentUser, UserRole, get_current_user


@pytest.mark.asyncio
async def test_get_profile_returns_persona(async_client: AsyncClient, app):
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="persona@valdrix.io",
        role=UserRole.ADMIN,
        tier="pro",
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
        tier="pro",
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
        tier="pro",
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put(
            "/api/v1/settings/profile", json={"persona": "unknown"}
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
