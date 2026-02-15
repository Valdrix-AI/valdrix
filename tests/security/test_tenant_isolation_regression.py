import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.aws_connection import AWSConnection
from app.models.notification_settings import NotificationSettings
from app.models.tenant import Tenant
from app.modules.governance.domain.security.audit_log import (
    AuditEventType,
    AuditLogger,
    AuditLog,
)
from app.shared.core.auth import CurrentUser, UserRole, get_current_user


@pytest.mark.asyncio
async def test_connections_list_is_tenant_scoped(async_client: AsyncClient, db, app):
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant A", plan="pro")
    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant B", plan="pro")
    db.add_all([tenant_a, tenant_b])
    await db.commit()

    db.add_all(
        [
            AWSConnection(
                tenant_id=tenant_a.id,
                aws_account_id="111111111111",
                role_arn="arn:aws:iam::111111111111:role/ValdrixReadOnly",
                external_id="vx-" + ("a" * 32),
                region="us-east-1",
                status="active",
            ),
            AWSConnection(
                tenant_id=tenant_b.id,
                aws_account_id="222222222222",
                role_arn="arn:aws:iam::222222222222:role/ValdrixReadOnly",
                external_id="vx-" + ("b" * 32),
                region="us-east-1",
                status="active",
            ),
        ]
    )
    await db.commit()

    current_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email="user-a@valdrix.io",
        role=UserRole.MEMBER,
        tier="pro",
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        response = await async_client.get("/api/v1/settings/connections/aws")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert [row["aws_account_id"] for row in payload] == ["111111111111"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_notification_settings_get_is_tenant_scoped(
    async_client: AsyncClient, db, app
):
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant Notif A", plan="pro")
    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant Notif B", plan="pro")
    db.add_all([tenant_a, tenant_b])
    await db.commit()

    db.add_all(
        [
            NotificationSettings(
                tenant_id=tenant_a.id,
                slack_enabled=True,
                jira_enabled=False,
                jira_issue_type="Task",
                digest_schedule="daily",
                digest_hour=9,
                digest_minute=0,
                alert_on_budget_warning=True,
                alert_on_budget_exceeded=True,
                alert_on_zombie_detected=True,
            ),
            NotificationSettings(
                tenant_id=tenant_b.id,
                slack_enabled=False,
                jira_enabled=False,
                jira_issue_type="Task",
                digest_schedule="weekly",
                digest_hour=8,
                digest_minute=0,
                alert_on_budget_warning=False,
                alert_on_budget_exceeded=False,
                alert_on_zombie_detected=False,
            ),
        ]
    )
    await db.commit()

    current_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_b.id,
        email="user-b@valdrix.io",
        role=UserRole.MEMBER,
        tier="pro",
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        response = await async_client.get("/api/v1/settings/notifications")
        assert response.status_code == 200
        payload = response.json()
        assert payload["slack_enabled"] is False
        assert payload["digest_schedule"] == "weekly"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_audit_logs_endpoint_is_tenant_scoped(async_client: AsyncClient, db, app):
    tenant_a = Tenant(id=uuid.uuid4(), name="Tenant Audit A", plan="pro")
    tenant_b = Tenant(id=uuid.uuid4(), name="Tenant Audit B", plan="pro")
    db.add_all([tenant_a, tenant_b])
    await db.commit()

    audit_a = AuditLogger(db=db, tenant_id=tenant_a.id, correlation_id="run-a")
    audit_b = AuditLogger(db=db, tenant_id=tenant_b.id, correlation_id="run-b")
    await audit_a.log(
        event_type=AuditEventType.SETTINGS_UPDATED,
        actor_id=None,
        actor_email="a@valdrix.io",
        resource_type="tenant",
        resource_id=str(tenant_a.id),
        details={"marker": "a"},
        request_method="GET",
        request_path="/api/v1/audit/logs",
    )
    await audit_b.log(
        event_type=AuditEventType.SETTINGS_UPDATED,
        actor_id=None,
        actor_email="b@valdrix.io",
        resource_type="tenant",
        resource_id=str(tenant_b.id),
        details={"marker": "b"},
        request_method="GET",
        request_path="/api/v1/audit/logs",
    )
    await db.commit()

    # Verify both exist in DB (sanity check).
    count = (await db.execute(select(AuditLog.id))).scalars().all()
    assert len(count) >= 2

    current_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        email="admin-a@valdrix.io",
        role=UserRole.ADMIN,
        tier="pro",
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        response = await async_client.get("/api/v1/audit/logs?limit=10")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        # Tenant B marker should not be visible to tenant A.
        assert all(row.get("correlation_id") != "run-b" for row in payload)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
