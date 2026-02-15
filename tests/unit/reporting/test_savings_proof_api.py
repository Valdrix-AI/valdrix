import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.optimization import OptimizationStrategy, StrategyRecommendation
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.models.realized_savings import RealizedSavingsEvent
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import create_access_token


@pytest.mark.asyncio
async def test_savings_proof_aggregates_opportunity_and_realized(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Savings Tenant", plan="pro")
    db.add(tenant)

    admin = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(admin)

    strategy_id = uuid.uuid4()
    strategy = OptimizationStrategy(
        id=strategy_id,
        name="RI",
        description="Reserved Instances",
        type="reserved_instance",
        provider="aws",
        config={},
        is_active=True,
    )
    db.add(strategy)

    open_rec = StrategyRecommendation(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        resource_type="m5.large",
        region="us-east-1",
        term="1_year",
        payment_option="no_upfront",
        upfront_cost=Decimal("0.00"),
        monthly_recurring_cost=Decimal("0.00"),
        estimated_monthly_savings=Decimal("10.00"),
        roi_percentage=Decimal("20.00"),
        status="open",
    )
    db.add(open_rec)

    applied_rec = StrategyRecommendation(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        resource_type="compute-sp",
        region="us-east-1",
        term="1_year",
        payment_option="no_upfront",
        upfront_cost=Decimal("0.00"),
        monthly_recurring_cost=Decimal("0.00"),
        estimated_monthly_savings=Decimal("5.00"),
        roi_percentage=Decimal("10.00"),
        status="applied",
        applied_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(applied_rec)

    pending_rem = RemediationRequest(
        tenant_id=tenant_id,
        resource_id="vol-123",
        resource_type="EBS Volume",
        provider="aws",
        region="us-east-1",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.PENDING,
        estimated_monthly_savings=Decimal("2.00"),
        requested_by_user_id=admin.id,
    )
    db.add(pending_rem)

    completed_rem = RemediationRequest(
        tenant_id=tenant_id,
        resource_id="i-123",
        resource_type="EC2 Instance",
        provider="aws",
        region="us-east-1",
        action=RemediationAction.TERMINATE_INSTANCE,
        status=RemediationStatus.COMPLETED,
        estimated_monthly_savings=Decimal("3.00"),
        requested_by_user_id=admin.id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(completed_rem)

    await db.commit()

    token = create_access_token({"sub": str(admin.id), "email": "admin@example.com"})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get("/api/v1/savings/proof", headers=headers)
    assert res.status_code == 200
    payload = res.json()

    assert payload["open_recommendations"] == 1
    assert payload["applied_recommendations"] == 1
    assert payload["pending_remediations"] == 1
    assert payload["completed_remediations"] == 1

    assert payload["opportunity_monthly_usd"] == 12.0
    assert payload["realized_monthly_usd"] == 8.0

    aws_breakdown = next(
        item for item in payload["breakdown"] if item["provider"] == "aws"
    )
    assert aws_breakdown["opportunity_monthly_usd"] == 12.0
    assert aws_breakdown["realized_monthly_usd"] == 8.0


@pytest.mark.asyncio
async def test_savings_proof_drilldown_strategy_type_and_remediation_action(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Drilldown Tenant", plan="pro")
    db.add(tenant)

    admin = User(
        id=uuid.uuid4(),
        email="admin2@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN.value,
    )
    db.add(admin)

    strategy_id = uuid.uuid4()
    strategy = OptimizationStrategy(
        id=strategy_id,
        name="RI",
        description="Reserved Instances",
        type="reserved_instance",
        provider="aws",
        config={},
        is_active=True,
    )
    db.add(strategy)

    open_rec = StrategyRecommendation(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        resource_type="m5.large",
        region="us-east-1",
        term="1_year",
        payment_option="no_upfront",
        upfront_cost=Decimal("0.00"),
        monthly_recurring_cost=Decimal("0.00"),
        estimated_monthly_savings=Decimal("10.00"),
        roi_percentage=Decimal("20.00"),
        status="open",
    )
    db.add(open_rec)

    applied_rec = StrategyRecommendation(
        tenant_id=tenant_id,
        strategy_id=strategy_id,
        resource_type="compute-sp",
        region="us-east-1",
        term="1_year",
        payment_option="no_upfront",
        upfront_cost=Decimal("0.00"),
        monthly_recurring_cost=Decimal("0.00"),
        estimated_monthly_savings=Decimal("5.00"),
        roi_percentage=Decimal("10.00"),
        status="applied",
        applied_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(applied_rec)

    pending_delete = RemediationRequest(
        tenant_id=tenant_id,
        resource_id="vol-999",
        resource_type="EBS Volume",
        provider="aws",
        region="us-east-1",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.PENDING,
        estimated_monthly_savings=Decimal("2.00"),
        requested_by_user_id=admin.id,
    )
    db.add(pending_delete)

    pending_stop = RemediationRequest(
        tenant_id=tenant_id,
        resource_id="i-999",
        resource_type="EC2 Instance",
        provider="aws",
        region="us-east-1",
        action=RemediationAction.STOP_INSTANCE,
        status=RemediationStatus.APPROVED,
        estimated_monthly_savings=Decimal("4.00"),
        requested_by_user_id=admin.id,
    )
    db.add(pending_stop)

    completed_rem = RemediationRequest(
        tenant_id=tenant_id,
        resource_id="i-777",
        resource_type="EC2 Instance",
        provider="aws",
        region="us-east-1",
        action=RemediationAction.TERMINATE_INSTANCE,
        status=RemediationStatus.COMPLETED,
        estimated_monthly_savings=Decimal("3.00"),
        requested_by_user_id=admin.id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.add(completed_rem)
    await db.flush()

    # Finance-grade realized savings evidence should override the estimate for completed remediations.
    evidence = RealizedSavingsEvent(
        tenant_id=tenant_id,
        remediation_request_id=completed_rem.id,
        provider="aws",
        account_id=None,
        resource_id=completed_rem.resource_id,
        service="ec2",
        region=completed_rem.region,
        baseline_start_date=(datetime.now(timezone.utc) - timedelta(days=20)).date(),
        baseline_end_date=(datetime.now(timezone.utc) - timedelta(days=14)).date(),
        measurement_start_date=(datetime.now(timezone.utc) - timedelta(days=12)).date(),
        measurement_end_date=(datetime.now(timezone.utc) - timedelta(days=6)).date(),
        baseline_total_cost_usd=Decimal("100.00"),
        baseline_observed_days=7,
        measurement_total_cost_usd=Decimal("80.00"),
        measurement_observed_days=7,
        baseline_avg_daily_cost_usd=Decimal("14.2857"),
        measurement_avg_daily_cost_usd=Decimal("11.4286"),
        realized_avg_daily_savings_usd=Decimal("2.8571"),
        realized_monthly_savings_usd=Decimal("20.00"),
        monthly_multiplier_days=30,
        confidence_score=Decimal("0.80"),
        details={"test": True},
        computed_at=datetime.now(timezone.utc),
    )
    db.add(evidence)

    await db.commit()

    token = create_access_token({"sub": str(admin.id), "email": admin.email})
    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get(
        "/api/v1/savings/proof/drilldown?dimension=strategy_type", headers=headers
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["dimension"] == "strategy_type"
    reserved = next(
        item for item in payload["buckets"] if item["key"] == "reserved_instance"
    )
    assert reserved["open_recommendations"] == 1
    assert reserved["applied_recommendations"] == 1
    assert reserved["opportunity_monthly_usd"] == 10.0
    assert reserved["realized_monthly_usd"] == 5.0

    res = await ac.get(
        "/api/v1/savings/proof/drilldown?dimension=remediation_action", headers=headers
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["dimension"] == "remediation_action"
    terminate = next(
        item for item in payload["buckets"] if item["key"] == "terminate_instance"
    )
    assert terminate["completed_remediations"] == 1
    assert terminate["realized_monthly_usd"] == 20.0

    assert payload["opportunity_monthly_usd"] == 6.0
    assert payload["realized_monthly_usd"] == 20.0
