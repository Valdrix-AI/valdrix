import csv
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.aws_connection import AWSConnection
from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant
from app.modules.reporting.domain.focus_export import FOCUS_V13_CORE_COLUMNS
from app.shared.core.auth import CurrentUser, UserRole, get_current_user
from app.shared.core.pricing import PricingTier
from app.modules.reporting.api.v1 import costs as costs_api


@pytest.mark.asyncio
async def test_focus_export_returns_csv_with_expected_columns_and_ids(
    async_client: AsyncClient,
    app,
    db,
):
    tenant_id = uuid.uuid4()
    account_uuid = uuid.uuid4()

    tenant = Tenant(
        id=tenant_id, name="Focus Export Tenant", plan=PricingTier.PRO.value
    )
    db.add(tenant)

    aws_conn = AWSConnection(
        id=account_uuid,
        tenant_id=tenant_id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/ValdricsReadOnly",
        external_id="vx-test-external-id",
        region="us-east-1",
        status="active",
    )
    db.add(aws_conn)

    cloud_account = CloudAccount(
        id=account_uuid,
        tenant_id=tenant_id,
        provider="aws",
        name="Prod AWS",
        is_active=True,
    )
    db.add(cloud_account)

    record_day = date(2026, 1, 1)
    cost = Decimal("10.50")
    cost_record = CostRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        account_id=account_uuid,
        service="AmazonEC2",
        region="us-east-1",
        usage_type="BoxUsage:t3.micro",
        canonical_charge_category="compute",
        canonical_charge_subcategory="runtime",
        canonical_mapping_version="focus-1.3-v1",
        cost_usd=cost,
        amount_raw=cost,
        currency="USD",
        carbon_kg=None,
        is_preliminary=False,
        cost_status="FINAL",
        reconciliation_run_id=None,
        ingestion_metadata={"tags": {"env": "prod"}},
        attribution_id=None,
        allocated_to=None,
        recorded_at=record_day,
        timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    db.add(cost_record)

    await db.commit()

    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="focus-export@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs/export/focus",
            params={
                "start_date": record_day.isoformat(),
                "end_date": record_day.isoformat(),
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == FOCUS_V13_CORE_COLUMNS
        assert len(rows) == 2

        header = rows[0]
        data = rows[1]
        assert data[header.index("BillingAccountId")] == "123456789012"
        assert data[header.index("ProviderName")] == "Amazon Web Services"
        assert data[header.index("ServiceProviderName")] == "Amazon Web Services"
        assert data[header.index("ServiceCategory")] == "Compute"
        assert data[header.index("ServiceSubcategory")] == "Other (Compute)"
        assert data[header.index("ServiceName")] == "AmazonEC2"
        assert data[header.index("ChargeCategory")] == "Usage"
        assert data[header.index("ChargeClass")] == "Regular"
        assert data[header.index("ChargeFrequency")] == "Usage-Based"
        assert data[header.index("BillingCurrency")] == "USD"
        assert data[header.index("BilledCost")] == "10.50"
        assert data[header.index("Tags")] == '{"env":"prod"}'
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_focus_export_requires_compliance_exports_feature(
    async_client: AsyncClient, app
):
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="focus-export-denied@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs/export/focus",
            params={"start_date": "2026-01-01", "end_date": "2026-01-01"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_focus_export_rejects_date_window_beyond_limit(
    async_client: AsyncClient,
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="focus-export-window@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    monkeypatch.setattr(costs_api.get_settings(), "FOCUS_EXPORT_MAX_DAYS", 1)
    try:
        response = await async_client.get(
            "/api/v1/costs/export/focus",
            params={"start_date": "2026-01-01", "end_date": "2026-01-03"},
        )
        assert response.status_code == 400
        assert "Date window exceeds export limit" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
