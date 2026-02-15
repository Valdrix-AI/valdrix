import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_get_leadership_kpis_json_and_csv_filters_preliminary(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user
    from app.models.cloud import CloudAccount, CostRecord

    user = CurrentUser(
        id=uuid.uuid4(),
        email="leadership@valdrix.io",
        tenant_id=test_tenant.id,
        role="admin",
        tier="pro",
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        account = CloudAccount(
            tenant_id=test_tenant.id,
            provider="aws",
            name="Leadership AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        db.add_all(
            [
                CostRecord(
                    tenant_id=test_tenant.id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("100.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    is_preliminary=False,
                    cost_status="FINAL",
                    recorded_at=date(2026, 2, 1),
                    timestamp=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                ),
                CostRecord(
                    tenant_id=test_tenant.id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("50.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    is_preliminary=True,
                    cost_status="PRELIMINARY",
                    recorded_at=date(2026, 2, 1),
                    timestamp=datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await db.commit()

        res = await async_client.get(
            "/api/v1/leadership/kpis",
            params={"start_date": "2026-02-01", "end_date": "2026-02-01"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["total_cost_usd"] == 100.0
        assert body["cost_by_provider"]["aws"] == 100.0

        csv_res = await async_client.get(
            "/api/v1/leadership/kpis",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "response_format": "csv",
            },
        )
        assert csv_res.status_code == 200
        assert csv_res.headers.get("content-type", "").startswith("text/csv")
        assert "total_cost_usd" in csv_res.text
        assert "100.0000" in csv_res.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_capture_and_list_leadership_kpis_evidence(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user
    from app.models.cloud import CloudAccount, CostRecord
    from app.models.tenant import User
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )
    from sqlalchemy import select

    admin_user = CurrentUser(
        id=uuid.uuid4(),
        email="admin-leadership@valdrix.io",
        tenant_id=test_tenant.id,
        role="admin",
        tier="pro",
    )
    db.add(
        User(
            id=admin_user.id,
            tenant_id=test_tenant.id,
            email=admin_user.email,
            role="admin",
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        account = CloudAccount(
            tenant_id=test_tenant.id,
            provider="aws",
            name="Leadership AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()
        db.add(
            CostRecord(
                tenant_id=test_tenant.id,
                account_id=account.id,
                service="AmazonS3",
                region="us-east-1",
                usage_type="Storage",
                cost_usd=Decimal("25.00"),
                currency="USD",
                canonical_charge_category="storage",
                canonical_mapping_version="focus-1.3-v1",
                is_preliminary=False,
                cost_status="FINAL",
                recorded_at=date(2026, 2, 2),
                timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc),
            )
        )
        await db.commit()

        capture = await async_client.post(
            "/api/v1/leadership/kpis/capture",
            params={"start_date": "2026-02-01", "end_date": "2026-02-03"},
        )
        assert capture.status_code == 200
        body = capture.json()
        assert body["status"] == "captured"
        assert body["leadership_kpis"]["total_cost_usd"] == 25.0

        listed = await async_client.get(
            "/api/v1/leadership/kpis/evidence", params={"limit": 10}
        )
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["total"] >= 1
        assert payload["items"][0]["total_cost_usd"] >= 0

        row = await db.scalar(
            select(AuditLog).where(
                AuditLog.tenant_id == test_tenant.id,
                AuditLog.event_type == AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
            )
        )
        assert row is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)
