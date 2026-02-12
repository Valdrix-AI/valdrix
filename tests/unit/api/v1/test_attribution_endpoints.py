from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.attribution import CostAllocation
from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.core.pricing import PricingTier


@pytest_asyncio.fixture
async def admin_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Attribution Tenant", plan="pro")
    user = User(id=user_id, email="admin@attribution.io", tenant_id=tenant_id, role=UserRole.ADMIN)
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
    tenant = Tenant(id=tenant_id, name="Attribution Member Tenant", plan="pro")
    user = User(id=user_id, email="member@attribution.io", tenant_id=tenant_id, role=UserRole.MEMBER)
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )


@pytest.mark.asyncio
async def test_rule_crud_flow(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        create_payload = {
            "name": "S3 Split",
            "priority": 10,
            "rule_type": "PERCENTAGE",
            "conditions": {"service": "AmazonS3"},
            "allocation": [
                {"bucket": "Team-A", "percentage": 60},
                {"bucket": "Team-B", "percentage": 40},
            ],
            "is_active": True,
        }
        create_response = await async_client.post("/api/v1/attribution/rules", json=create_payload)
        assert create_response.status_code == 200
        created = create_response.json()
        rule_id = created["id"]
        assert created["rule_type"] == "PERCENTAGE"

        list_response = await async_client.get("/api/v1/attribution/rules")
        assert list_response.status_code == 200
        assert any(rule["id"] == rule_id for rule in list_response.json())

        patch_response = await async_client.patch(
            f"/api/v1/attribution/rules/{rule_id}",
            json={"priority": 1, "is_active": False},
        )
        assert patch_response.status_code == 200
        updated = patch_response.json()
        assert updated["priority"] == 1
        assert updated["is_active"] is False

        active_only_response = await async_client.get("/api/v1/attribution/rules")
        assert active_only_response.status_code == 200
        assert all(rule["id"] != rule_id for rule in active_only_response.json())

        include_inactive_response = await async_client.get("/api/v1/attribution/rules?include_inactive=true")
        assert include_inactive_response.status_code == 200
        assert any(rule["id"] == rule_id for rule in include_inactive_response.json())

        delete_response = await async_client.delete(f"/api/v1/attribution/rules/{rule_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_create_rule_rejects_invalid_percentage(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = await async_client.post(
            "/api/v1/attribution/rules",
            json={
                "name": "Broken Split",
                "priority": 5,
                "rule_type": "PERCENTAGE",
                "conditions": {"service": "AmazonS3"},
                "allocation": [
                    {"bucket": "Team-A", "percentage": 70},
                    {"bucket": "Team-B", "percentage": 20},
                ],
                "is_active": True,
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_simulate_rule_returns_projection(async_client, app, db, member_user):
    app.dependency_overrides[get_current_user] = lambda: member_user
    try:
        account = CloudAccount(
            tenant_id=member_user.tenant_id,
            provider="aws",
            name="Member AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        record_date = date(2026, 2, 1)
        db.add_all(
            [
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonS3",
                    region="us-east-1",
                    usage_type="TimedStorage-ByteHrs",
                    cost_usd=Decimal("50.00"),
                    currency="USD",
                    canonical_charge_category="storage",
                    canonical_mapping_version="focus-1.3-v1",
                    recorded_at=record_date,
                    timestamp=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                ),
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("20.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    recorded_at=record_date,
                    timestamp=datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await db.commit()

        response = await async_client.post(
            "/api/v1/attribution/simulate",
            json={
                "rule_type": "PERCENTAGE",
                "conditions": {"service": "AmazonS3"},
                "allocation": [
                    {"bucket": "Team-A", "percentage": 60},
                    {"bucket": "Team-B", "percentage": 40},
                ],
                "start_date": "2026-02-01",
                "end_date": "2026-02-01",
                "sample_limit": 100,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["matched_records"] == 1
        assert data["projected_allocation_total"] == 50.0
        assert len(data["projected_allocations"]) == 2
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_apply_rules_endpoint_creates_allocations(async_client, app, db, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        account = CloudAccount(
            tenant_id=admin_user.tenant_id,
            provider="aws",
            name="Admin AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        record_date = date(2026, 2, 2)
        record = CostRecord(
            tenant_id=admin_user.tenant_id,
            account_id=account.id,
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage",
            cost_usd=Decimal("80.00"),
            currency="USD",
            canonical_charge_category="compute",
            canonical_mapping_version="focus-1.3-v1",
            recorded_at=record_date,
            timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc),
        )
        db.add(record)
        await db.flush()

        create_rule_response = await async_client.post(
            "/api/v1/attribution/rules",
            json={
                "name": "EC2 Direct",
                "priority": 1,
                "rule_type": "DIRECT",
                "conditions": {"service": "AmazonEC2"},
                "allocation": {"bucket": "Platform"},
                "is_active": True,
            },
        )
        assert create_rule_response.status_code == 200

        apply_response = await async_client.post(
            "/api/v1/attribution/apply",
            json={"start_date": "2026-02-02", "end_date": "2026-02-02"},
        )
        assert apply_response.status_code == 200
        body = apply_response.json()
        assert body["status"] == "completed"
        assert body["records_processed"] >= 1
        assert body["allocations_created"] >= 1

        allocations_result = await db.execute(
            select(CostAllocation).where(
                CostAllocation.cost_record_id == record.id,
                CostAllocation.recorded_at == record.recorded_at,
            )
        )
        allocations = allocations_result.scalars().all()
        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Platform"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_rule_not_found(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = await async_client.patch(
            f"/api/v1/attribution/rules/{uuid4()}",
            json={"priority": 10},
        )
        assert response.status_code == 404
        assert response.json()["error"] == "Attribution rule not found"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_delete_rule_not_found(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = await async_client.delete(f"/api/v1/attribution/rules/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["error"] == "Attribution rule not found"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_simulate_rule_rejects_invalid_date_window(async_client, app, member_user):
    app.dependency_overrides[get_current_user] = lambda: member_user
    try:
        response = await async_client.post(
            "/api/v1/attribution/simulate",
            json={
                "rule_type": "DIRECT",
                "conditions": {"service": "AmazonS3"},
                "allocation": {"bucket": "A"},
                "start_date": "2026-02-02",
                "end_date": "2026-02-01",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "start_date must be <= end_date"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_simulate_rule_rejects_invalid_allocation(async_client, app, member_user):
    app.dependency_overrides[get_current_user] = lambda: member_user
    try:
        response = await async_client.post(
            "/api/v1/attribution/simulate",
            json={
                "rule_type": "PERCENTAGE",
                "conditions": {"service": "AmazonS3"},
                "allocation": [
                    {"bucket": "A", "percentage": 10},
                    {"bucket": "B", "percentage": 20},
                ],
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_apply_rules_rejects_invalid_window(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    try:
        response = await async_client.post(
            "/api/v1/attribution/apply",
            json={"start_date": "2026-02-02", "end_date": "2026-02-01"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "start_date must be <= end_date"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_attribution_requires_chargeback_feature(async_client, app):
    starter_user = CurrentUser(
        id=uuid4(),
        email="starter@attribution.io",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )
    app.dependency_overrides[get_current_user] = lambda: starter_user
    try:
        response = await async_client.get("/api/v1/attribution/rules")
        assert response.status_code == 403
        assert "upgrade" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
