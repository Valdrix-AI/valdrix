import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models.tenant import Tenant, User, UserRole
from app.models.optimization import (
    OptimizationStrategy,
    StrategyRecommendation,
    CommitmentTerm,
    PaymentOption,
)
from app.models.cloud import CloudAccount, CostRecord
from app.shared.core.auth import CurrentUser, get_current_user, require_tenant_access


@pytest_asyncio.fixture
async def admin_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Test Tenant", plan="pro")
    user = User(
        id=user_id, email="admin@test.io", tenant_id=tenant_id, role=UserRole.ADMIN
    )
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier="pro",
    )


@pytest_asyncio.fixture
async def member_user(db):
    tenant_id = uuid4()
    user_id = uuid4()
    tenant = Tenant(id=tenant_id, name="Member Tenant", plan="pro")
    user = User(
        id=user_id, email="member@test.io", tenant_id=tenant_id, role=UserRole.MEMBER
    )
    db.add_all([tenant, user])
    await db.commit()
    return CurrentUser(
        id=user_id,
        email=user.email,
        tenant_id=tenant_id,
        role=UserRole.MEMBER,
        tier="pro",
    )


@pytest.mark.asyncio
async def test_list_recommendations_filters_and_orders(
    async_client, db, app, member_user
):
    app.dependency_overrides[get_current_user] = lambda: member_user
    app.dependency_overrides[require_tenant_access] = lambda: member_user.tenant_id

    strategy = OptimizationStrategy(
        name="RI",
        description="test",
        type="reserved_instance",
        provider="aws",
    )
    db.add(strategy)
    await db.flush()

    rec_open_low = StrategyRecommendation(
        tenant_id=member_user.tenant_id,
        strategy_id=strategy.id,
        resource_type="m5.large",
        region="us-east-1",
        term=CommitmentTerm.ONE_YEAR,
        payment_option=PaymentOption.NO_UPFRONT,
        upfront_cost=0.0,
        monthly_recurring_cost=10.0,
        estimated_monthly_savings=5.0,
        estimated_monthly_savings_low=4.0,
        estimated_monthly_savings_high=6.0,
        break_even_months=0.0,
        confidence_score=0.82,
        roi_percentage=10.0,
        status="open",
    )
    rec_open_high = StrategyRecommendation(
        tenant_id=member_user.tenant_id,
        strategy_id=strategy.id,
        resource_type="m5.xlarge",
        region="us-east-1",
        term=CommitmentTerm.ONE_YEAR,
        payment_option=PaymentOption.NO_UPFRONT,
        upfront_cost=0.0,
        monthly_recurring_cost=20.0,
        estimated_monthly_savings=15.0,
        estimated_monthly_savings_low=12.0,
        estimated_monthly_savings_high=18.0,
        break_even_months=0.0,
        confidence_score=0.93,
        roi_percentage=30.0,
        status="open",
    )
    rec_applied = StrategyRecommendation(
        tenant_id=member_user.tenant_id,
        strategy_id=strategy.id,
        resource_type="m5.2xlarge",
        region="us-east-1",
        term=CommitmentTerm.ONE_YEAR,
        payment_option=PaymentOption.NO_UPFRONT,
        upfront_cost=0.0,
        monthly_recurring_cost=30.0,
        estimated_monthly_savings=25.0,
        estimated_monthly_savings_low=20.0,
        estimated_monthly_savings_high=30.0,
        break_even_months=0.0,
        confidence_score=0.95,
        roi_percentage=50.0,
        status="applied",
    )

    db.add_all([rec_open_low, rec_open_high, rec_applied])
    await db.commit()

    response = await async_client.get("/api/v1/strategies/recommendations?status=open")
    assert response.status_code == 200
    data = response.json()
    assert [rec["resource_type"] for rec in data] == ["m5.xlarge", "m5.large"]
    assert data[0]["estimated_monthly_savings_low"] == 12.0
    assert data[0]["estimated_monthly_savings_high"] == 18.0
    assert data[0]["break_even_months"] == 0.0
    assert data[0]["confidence_score"] == 0.93

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant_access, None)


@pytest.mark.asyncio
async def test_apply_recommendation_updates_status(async_client, db, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_tenant_access] = lambda: admin_user.tenant_id

    strategy = OptimizationStrategy(
        name="RI",
        description="test",
        type="reserved_instance",
        provider="aws",
    )
    db.add(strategy)
    await db.flush()

    rec = StrategyRecommendation(
        tenant_id=admin_user.tenant_id,
        strategy_id=strategy.id,
        resource_type="m5.large",
        region="us-east-1",
        term=CommitmentTerm.ONE_YEAR,
        payment_option=PaymentOption.NO_UPFRONT,
        upfront_cost=0.0,
        monthly_recurring_cost=10.0,
        estimated_monthly_savings=5.0,
        roi_percentage=10.0,
        status="open",
    )
    db.add(rec)
    await db.commit()

    response = await async_client.post(f"/api/v1/strategies/apply/{rec.id}")
    assert response.status_code == 200
    await db.refresh(rec)
    assert rec.status == "applied"
    assert rec.applied_at is not None

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant_access, None)


@pytest.mark.asyncio
async def test_apply_recommendation_not_found(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_tenant_access] = lambda: admin_user.tenant_id

    missing_id = uuid4()
    response = await async_client.post(f"/api/v1/strategies/apply/{missing_id}")
    assert response.status_code == 404

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant_access, None)


@pytest.mark.asyncio
async def test_trigger_optimization_scan(async_client, app, admin_user):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_tenant_access] = lambda: admin_user.tenant_id

    with patch(
        "app.modules.optimization.api.v1.strategies.OptimizationService"
    ) as mock_service:
        mock_service.return_value.generate_recommendations = AsyncMock(
            return_value=[{"id": "1"}, {"id": "2"}]
        )
        response = await async_client.post("/api/v1/strategies/refresh")

    assert response.status_code == 200
    data = response.json()
    assert data["recommendations_generated"] == 2

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_tenant_access, None)


@pytest.mark.asyncio
async def test_strategies_requires_commitment_optimization_feature(
    async_client, app
) -> None:
    starter_user = CurrentUser(
        id=uuid4(),
        email="starter@valdrix.io",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
        tier="starter",
    )
    app.dependency_overrides[get_current_user] = lambda: starter_user
    app.dependency_overrides[require_tenant_access] = lambda: starter_user.tenant_id
    try:
        response = await async_client.get(
            "/api/v1/strategies/recommendations?status=open"
        )
        assert response.status_code == 403
        assert "upgrade" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_tenant_access, None)


@pytest.mark.asyncio
async def test_backtest_endpoint_returns_strategy_results(
    async_client, db, app, member_user
) -> None:
    app.dependency_overrides[get_current_user] = lambda: member_user
    app.dependency_overrides[require_tenant_access] = lambda: member_user.tenant_id
    try:
        account = CloudAccount(
            tenant_id=member_user.tenant_id,
            provider="aws",
            name="Backtest AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()

        # Daily-resolution ledger rows (timestamp is optional). The service expands these
        # into hourly series for the backtest harness.
        from datetime import date
        from decimal import Decimal

        db.add_all(
            [
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("24.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    is_preliminary=False,
                    cost_status="FINAL",
                    recorded_at=date(2026, 2, 10),
                    timestamp=None,
                ),
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("24.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    is_preliminary=False,
                    cost_status="FINAL",
                    recorded_at=date(2026, 2, 11),
                    timestamp=None,
                ),
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("24.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    is_preliminary=False,
                    cost_status="FINAL",
                    recorded_at=date(2026, 2, 12),
                    timestamp=None,
                ),
            ]
        )

        strategy = OptimizationStrategy(
            name="Compute Savings Plan",
            description="test",
            type="savings_plan",
            provider="aws",
            config={"min_hourly_threshold": 0.01, "backtest_tolerance": 0.30},
            is_active=True,
        )
        db.add(strategy)
        await db.commit()

        response = await async_client.get(
            "/api/v1/strategies/backtest",
            params={"provider": "aws", "strategy_type": "savings_plan", "days": 7},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "success"
        assert len(payload["strategies"]) == 1
        assert payload["strategies"][0]["provider"] == "aws"
        assert payload["strategies"][0]["strategy_type"] == "savings_plan"
        assert "within_tolerance" in payload["strategies"][0]["backtest"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_tenant_access, None)
