from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.cloud import CloudAccount, CostRecord
from app.models.invoice import ProviderInvoice
from app.models.tenant import Tenant, User, UserRole
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLog
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest_asyncio.fixture
async def admin_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Invoice Tenant", plan="pro")
    user = User(
        id=user_id, email="admin@invoice.io", tenant_id=tenant_id, role=UserRole.ADMIN
    )
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


@pytest.mark.asyncio
async def test_upsert_list_patch_delete_invoice_flow(async_client, app, db, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        upsert = await async_client.post(
            "/api/v1/costs/reconciliation/invoices",
            json={
                "provider": "aws",
                "start_date": "2026-02-01",
                "end_date": "2026-02-28",
                "currency": "USD",
                "total_amount": 123.45,
                "invoice_number": "INV-001",
                "status": "submitted",
                "notes": "upload via finance close",
            },
        )
        assert upsert.status_code == 200
        payload = upsert.json()
        assert payload["status"] == "success"
        invoice_id = payload["invoice"]["id"]

        listed = await async_client.get(
            "/api/v1/costs/reconciliation/invoices?provider=aws"
        )
        assert listed.status_code == 200
        assert any(item["id"] == invoice_id for item in listed.json())

        patched = await async_client.patch(
            f"/api/v1/costs/reconciliation/invoices/{invoice_id}",
            json={"status": "reconciled", "notes": "close complete"},
        )
        assert patched.status_code == 200
        assert patched.json()["invoice_status"] == "reconciled"

        deleted = await async_client.delete(
            f"/api/v1/costs/reconciliation/invoices/{invoice_id}"
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "deleted"

        rows = (
            (
                await db.execute(
                    select(ProviderInvoice).where(
                        ProviderInvoice.id == UUID(invoice_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows == []

        audit_rows = await db.execute(
            select(AuditLog.event_type).where(
                AuditLog.tenant_id == admin_user.tenant_id
            )
        )
        event_types = [row[0] for row in audit_rows.all()]
        assert AuditEventType.INVOICE_UPSERTED.value in event_types
        assert AuditEventType.INVOICE_STATUS_UPDATED.value in event_types
        assert AuditEventType.INVOICE_DELETED.value in event_types
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_package_includes_invoice_reconciliation_when_present(
    async_client, app, db, admin_user
):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        account = CloudAccount(
            tenant_id=admin_user.tenant_id,
            provider="aws",
            name="Invoice AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        # One finalized ledger row.
        record_date = date(2026, 2, 1)
        db.add(
            CostRecord(
                tenant_id=admin_user.tenant_id,
                account_id=account.id,
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
                cost_usd=Decimal("50.00"),
                currency="USD",
                canonical_charge_category="compute",
                canonical_mapping_version="focus-1.3-v1",
                is_preliminary=False,
                cost_status="FINAL",
                recorded_at=record_date,
                timestamp=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                ingestion_metadata={"source_adapter": "cur"},
            )
        )
        await db.commit()

        # Store invoice total to match ledger.
        await async_client.post(
            "/api/v1/costs/reconciliation/invoices",
            json={
                "provider": "aws",
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "currency": "USD",
                "total_amount": 50.0,
                "status": "submitted",
            },
        )

        response = await async_client.get(
            "/api/v1/costs/reconciliation/close-package",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "provider": "aws",
                "enforce_finalized": "true",
            },
        )
        assert response.status_code == 200
        package = response.json()
        assert package["close_status"] in {"ready", "blocked_preliminary_data"}
        assert package["invoice_reconciliation"]["status"] == "match"
        assert package["invoice_reconciliation"]["ledger_final_cost_usd"] == 50.0
        assert package["invoice_reconciliation"]["invoice"]["total_amount_usd"] == 50.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_package_csv_includes_invoice_reconciliation_section(
    async_client, app, db, admin_user
):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        account = CloudAccount(
            tenant_id=admin_user.tenant_id,
            provider="aws",
            name="Invoice AWS CSV",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        record_date = date(2026, 2, 1)
        db.add(
            CostRecord(
                tenant_id=admin_user.tenant_id,
                account_id=account.id,
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
                cost_usd=Decimal("50.00"),
                currency="USD",
                canonical_charge_category="compute",
                canonical_mapping_version="focus-1.3-v1",
                is_preliminary=False,
                cost_status="FINAL",
                recorded_at=record_date,
                timestamp=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                ingestion_metadata={"source_adapter": "cur"},
            )
        )
        await db.commit()

        await async_client.post(
            "/api/v1/costs/reconciliation/invoices",
            json={
                "provider": "aws",
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "currency": "USD",
                "total_amount": 50.0,
                "status": "submitted",
            },
        )

        response = await async_client.get(
            "/api/v1/costs/reconciliation/close-package",
            params={
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "provider": "aws",
                "response_format": "csv",
                "enforce_finalized": "true",
            },
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "invoice_reconciliation,status,match" in response.text
        assert "invoice_reconciliation,invoice_total_amount_usd,50.0" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
