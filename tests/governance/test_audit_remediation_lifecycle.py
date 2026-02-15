import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.models.tenant import Tenant, User
from app.modules.governance.domain.security.audit_log import AuditLog


@pytest.mark.asyncio
async def test_remediation_lifecycle_audit(db: AsyncSession):
    """
    Test a full remediation lifecycle: Request -> Audit Log Presence.
    (Issue R1: E2E scenario for zombie lifecycle)
    """
    tenant_id = uuid4()
    user_id = uuid4()

    # Pre-create tenant and user to avoid FK violation
    db.add(Tenant(id=tenant_id, name="Lifecycle Test Tenant", plan="enterprise"))
    db.add(User(id=user_id, email="admin@test.com", tenant_id=tenant_id))
    await db.commit()

    # 1. Create a Remediation Request
    request = RemediationRequest(
        id=uuid4(),
        tenant_id=tenant_id,
        connection_id=uuid4(),
        resource_id="vol-0123456789abc",
        resource_type="ebs_volume",
        action=RemediationAction.DELETE_VOLUME,
        estimated_monthly_savings=15.50,
        status=RemediationStatus.PENDING,
        requested_by_user_id=user_id,
    )
    db.add(request)

    # 2. Simulate Audit Logging
    audit = AuditLog(
        tenant_id=tenant_id,
        actor_id=user_id,
        actor_email="admin@test.com",
        event_type="remediation_request_created",
        event_timestamp=datetime.now(),  # Use naive to match schema
        resource_type="remediation",
        resource_id=str(request.id),
        success=True,
        details={"action": "delete", "resource": "vol-0123456789abc"},
    )
    db.add(audit)
    await db.commit()

    # 3. Verify Lifecycle Status
    result = await db.execute(
        select(RemediationRequest).where(RemediationRequest.id == request.id)
    )
    saved_request = result.scalar_one()
    assert saved_request.status == RemediationStatus.PENDING
    assert float(saved_request.estimated_monthly_savings) == 15.50

    # 4. Verify Audit Presence
    audit_result = await db.execute(
        select(AuditLog).where(
            AuditLog.resource_id == str(request.id),
            AuditLog.event_type == "remediation_request_created",
        )
    )
    saved_audit = audit_result.scalar_one()
    assert saved_audit.actor_email == "admin@test.com"
    assert saved_audit.success is True
    assert saved_audit.details["resource"] == "vol-0123456789abc"


@pytest.mark.asyncio
async def test_audit_log_masking_integrity(db: AsyncSession):
    """
    Verify that audit logs can hold complex details without corruption.
    """
    tenant_id = uuid4()
    db.add(Tenant(id=tenant_id, name="Masking Test Tenant", plan="enterprise"))
    await db.commit()

    log = AuditLog(
        tenant_id=tenant_id,
        event_type="security_event",
        event_timestamp=datetime.now(),
        details={"sensitive_key": "**********", "public_info": "region-us-east-1"},
        success=True,
    )
    db.add(log)
    await db.commit()

    result = await db.execute(select(AuditLog).where(AuditLog.tenant_id == tenant_id))
    saved_log = result.scalar_one()
    assert saved_log.details["sensitive_key"] == "**********"
    assert saved_log.details["public_info"] == "region-us-east-1"
