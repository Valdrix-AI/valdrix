import uuid
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cloud import CloudAccount, CostRecord
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.models.saas_connection import SaaSConnection
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import create_access_token


@pytest.mark.asyncio
async def test_realized_savings_compute_and_savings_proof_uses_ledger_delta(
    ac: AsyncClient,
    db: AsyncSession,
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Realized Savings Tenant", plan="pro")
    db.add(tenant)

    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(admin)

    conn_id = uuid.uuid4()
    saas_conn = SaaSConnection(
        id=conn_id,
        tenant_id=tenant_id,
        name="Stripe Billing",
        vendor="stripe",
        auth_method="manual",
        spend_feed=[],
        is_active=True,
    )
    db.add(saas_conn)

    cloud_account = CloudAccount(
        id=conn_id,
        tenant_id=tenant_id,
        provider="saas",
        name="Stripe Billing",
        is_active=True,
    )
    db.add(cloud_account)

    # Execute far enough in the past for the 7d baseline + 1d gap + 7d measurement windows.
    executed_at = datetime.now(timezone.utc) - timedelta(days=20)
    resource_id = "inv_123"

    request = RemediationRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        resource_id=resource_id,
        resource_type="SaaS Invoice",
        provider="saas",
        region="global",
        action=RemediationAction.MANUAL_REVIEW,
        status=RemediationStatus.COMPLETED,
        estimated_monthly_savings=Decimal(
            "1.00"
        ),  # Should be ignored when realized evidence exists
        requested_by_user_id=admin.id,
        connection_id=conn_id,
        executed_at=executed_at,
    )
    db.add(request)

    # v1 realized savings windows:
    # baseline: executed_day-7 .. executed_day-1  (10 USD/day)
    # measurement: executed_day+1 .. executed_day+7 (6 USD/day)
    executed_day = executed_at.date()
    baseline_start = executed_day - timedelta(days=7)
    baseline_end = executed_day - timedelta(days=1)
    measurement_start = executed_day + timedelta(days=1)
    measurement_end = executed_day + timedelta(days=7)

    def add_daily_cost(day: date, cost: Decimal) -> None:
        db.add(
            CostRecord(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                account_id=conn_id,
                service="Stripe Billing",
                region="global",
                usage_type="subscription_invoice",
                resource_id=resource_id,
                cost_usd=cost,
                amount_raw=cost,
                currency="USD",
                carbon_kg=None,
                is_preliminary=False,
                cost_status="FINAL",
                reconciliation_run_id=None,
                ingestion_metadata={"tags": {"vendor": "stripe"}},
                tags={"vendor": "stripe"},
                attribution_id=None,
                allocated_to=None,
                recorded_at=day,
                timestamp=datetime(day.year, day.month, day.day, tzinfo=timezone.utc),
                canonical_charge_category="unmapped",
                canonical_charge_subcategory=None,
                canonical_mapping_version="focus-1.3-v1",
            )
        )

    day = baseline_start
    while day <= baseline_end:
        add_daily_cost(day, Decimal("10.00"))
        day += timedelta(days=1)

    day = measurement_start
    while day <= measurement_end:
        add_daily_cost(day, Decimal("6.00"))
        day += timedelta(days=1)

    await db.commit()

    token = create_access_token({"sub": str(admin.id), "email": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    # Compute and persist realized savings evidence.
    res = await ac.post(
        "/api/v1/savings/realized/compute",
        params={
            "start_date": executed_day.isoformat(),
            "end_date": executed_day.isoformat(),
        },
        headers=headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["computed"] == 1

    # Savings proof should now use the ledger delta (120/mo) instead of estimated (1/mo).
    res = await ac.get(
        "/api/v1/savings/proof",
        params={
            "start_date": (executed_day - timedelta(days=1)).isoformat(),
            "end_date": (executed_day + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert res.status_code == 200
    report = res.json()
    assert report["completed_remediations"] == 1
    assert report["realized_monthly_usd"] == 120.0

    saas_breakdown = next(
        item for item in report["breakdown"] if item["provider"] == "saas"
    )
    assert saas_breakdown["realized_monthly_usd"] == 120.0

    # Realized savings evidence list endpoint (JSON + CSV)
    res = await ac.get(
        "/api/v1/savings/realized/events",
        params={
            "start_date": executed_day.isoformat(),
            "end_date": executed_day.isoformat(),
        },
        headers=headers,
    )
    assert res.status_code == 200
    events = res.json()
    assert len(events) == 1
    assert events[0]["realized_monthly_savings_usd"] == 120.0

    res = await ac.get(
        "/api/v1/savings/realized/events",
        params={
            "start_date": executed_day.isoformat(),
            "end_date": executed_day.isoformat(),
            "response_format": "csv",
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "realized_monthly_savings_usd" in res.text.splitlines()[0]
