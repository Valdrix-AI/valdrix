from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant, User, UserRole
from app.models.unit_economics_settings import UnitEconomicsSettings
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest_asyncio.fixture
async def admin_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Unit Econ Tenant", plan="pro")
    user = User(id=user_id, email="admin@unit-econ.io", tenant_id=tenant_id, role=UserRole.ADMIN)
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


@pytest_asyncio.fixture
async def member_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Unit Econ Member Tenant", plan="pro")
    user = User(id=user_id, email="member@unit-econ.io", tenant_id=tenant_id, role=UserRole.MEMBER)
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )


async def _seed_costs(db, tenant_id):
    account = CloudAccount(
        tenant_id=tenant_id,
        provider="aws",
        name="Unit Econ AWS",
        is_active=True,
    )
    db.add(account)
    await db.flush()

    def add_cost(day: date, amount: str, hour: int) -> None:
        db.add(
            CostRecord(
                tenant_id=tenant_id,
                account_id=account.id,
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
                cost_usd=Decimal(amount),
                currency="USD",
                canonical_charge_category="compute",
                canonical_mapping_version="focus-1.3-v1",
                recorded_at=day,
                timestamp=datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc),
            )
        )

    # Previous window total: 350.00 (Jan 25-31)
    for idx, day in enumerate(range(25, 32), start=1):
        add_cost(date(2026, 1, day), "50.00", idx)

    # Current window total: 700.00 (Feb 1-7)
    for idx, day in enumerate(range(1, 8), start=1):
        add_cost(date(2026, 2, day), "100.00", idx)

    await db.commit()


@pytest.mark.asyncio
async def test_unit_economics_settings_lifecycle(async_client, app, db, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = await async_client.get("/api/v1/costs/unit-economics/settings")
        assert response.status_code == 200
        data = response.json()
        assert data["default_request_volume"] == 1000.0
        assert data["anomaly_threshold_percent"] == 20.0

        update_response = await async_client.put(
            "/api/v1/costs/unit-economics/settings",
            json={
                "default_request_volume": 2000.0,
                "default_workload_volume": 80.0,
                "default_customer_volume": 25.0,
                "anomaly_threshold_percent": 30.0,
            },
        )
        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["default_request_volume"] == 2000.0
        assert updated["default_workload_volume"] == 80.0
        assert updated["default_customer_volume"] == 25.0
        assert updated["anomaly_threshold_percent"] == 30.0

        settings_row = await db.get(UnitEconomicsSettings, UUID(updated["id"]))
        assert settings_row is not None
        assert float(settings_row.default_request_volume) == 2000.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unit_economics_reports_anomalies_and_dispatches_alert(async_client, app, db, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        await _seed_costs(db, admin_user.tenant_id)

        # Tight denominator to make anomaly signal obvious (cost/unit doubles).
        await async_client.put(
            "/api/v1/costs/unit-economics/settings",
            json={
                "default_request_volume": 100.0,
                "default_workload_volume": 50.0,
                "default_customer_volume": 20.0,
                "anomaly_threshold_percent": 20.0,
            },
        )

        with patch(
            "app.modules.reporting.api.v1.costs.NotificationDispatcher.send_alert",
            new=AsyncMock(),
        ) as mock_alert:
            response = await async_client.get(
                "/api/v1/costs/unit-economics",
                params={"start_date": "2026-02-01", "end_date": "2026-02-07"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["total_cost"] == 700.0
        assert body["baseline_total_cost"] == 350.0
        assert len(body["metrics"]) == 3
        assert body["anomaly_count"] >= 1
        assert body["alert_dispatched"] is True
        assert mock_alert.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unit_economics_allows_alert_suppression(async_client, app, db, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        await _seed_costs(db, admin_user.tenant_id)
        await async_client.put(
            "/api/v1/costs/unit-economics/settings",
            json={
                "default_request_volume": 100.0,
                "default_workload_volume": 50.0,
                "default_customer_volume": 20.0,
                "anomaly_threshold_percent": 20.0,
            },
        )

        with patch(
            "app.modules.reporting.api.v1.costs.NotificationDispatcher.send_alert",
            new=AsyncMock(),
        ) as mock_alert:
            response = await async_client.get(
                "/api/v1/costs/unit-economics",
                params={
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-07",
                    "alert_on_anomaly": "false",
                },
            )

        assert response.status_code == 200
        assert response.json()["anomaly_count"] >= 1
        assert response.json()["alert_dispatched"] is False
        assert mock_alert.await_count == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_unit_economics_settings_update_requires_admin(async_client, app, member_user):
    app.dependency_overrides[get_current_user] = lambda: member_user
    try:
        response = await async_client.put(
            "/api/v1/costs/unit-economics/settings",
            json={"default_request_volume": 123.0},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
