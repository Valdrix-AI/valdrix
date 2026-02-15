from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_costs_endpoint_supports_saas_provider_filter(
    async_client, app, db
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Cloud Plus Tenant", plan="pro")
    user = User(
        id=user_id,
        email="cloudplus@valdrix.io",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
    )
    db.add_all([tenant, user])
    await db.flush()

    saas_account = CloudAccount(
        tenant_id=tenant_id,
        provider="saas",
        name="SaaS Spend Feed",
        is_active=True,
    )
    db.add(saas_account)
    await db.flush()

    db.add(
        CostRecord(
            tenant_id=tenant_id,
            account_id=saas_account.id,
            service="Slack",
            region="global",
            usage_type="subscription",
            cost_usd=Decimal("75.00"),
            currency="USD",
            canonical_charge_category="saas",
            canonical_mapping_version="focus-1.3-v1",
            recorded_at=date(2026, 1, 15),
            timestamp=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            cost_status="FINAL",
            is_preliminary=False,
        )
    )
    await db.commit()

    current_user = CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    try:
        response = await async_client.get(
            "/api/v1/costs",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "provider": "saas",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["provider"] == "saas"
        assert payload["total_cost"] == 75.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
