
import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.governance.domain.jobs.handlers.billing import RecurringBillingHandler
from app.models.background_job import BackgroundJob
# We need to mock the imports logic inside the handler
from app.modules.billing.domain.billing.paystack_billing import TenantSubscription
from app.models.pricing import PricingPlan

@pytest.mark.asyncio
async def test_execute_missing_subscription_id(db):
    handler = RecurringBillingHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={}
    )
    
    with pytest.raises(ValueError) as exc:
        await handler.execute(job, db)
    assert "subscription_id required" in str(exc.value)

@pytest.mark.asyncio
async def test_execute_subscription_not_found(db):
    handler = RecurringBillingHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"subscription_id": str(uuid4())}
    )
    
    # Mock DB execute to return None
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    
    result = await handler.execute(job, db)
    assert result["status"] == "failed"
    assert result["reason"] == "subscription_not_found"

@pytest.mark.asyncio
async def test_execute_subscription_inactive(db):
    handler = RecurringBillingHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"subscription_id": str(uuid4())}
    )
    
    sub = MagicMock(spec=TenantSubscription)
    sub.status = "canceled"
    
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sub)))
    
    result = await handler.execute(job, db)
    assert result["status"] == "skipped"
    assert "canceled" in result["reason"]

@pytest.mark.asyncio
async def test_execute_success(db):
    handler = RecurringBillingHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"subscription_id": str(uuid4())}
    )
    
    sub = MagicMock(spec=TenantSubscription)
    sub.status = "active"
    sub.tier = uuid4()
    
    plan_obj = MagicMock(spec=PricingPlan)
    plan_obj.price_usd = 29.99
    
    # DB calls: 1. Get Sub, 2. Get Plan
    mock_res_sub = MagicMock(scalar_one_or_none=MagicMock(return_value=sub))
    mock_res_plan = MagicMock(scalar_one_or_none=MagicMock(return_value=plan_obj))
    
    db.execute = AsyncMock(side_effect=[mock_res_sub, mock_res_plan])
    
    # Mock BillingService
    with patch("app.modules.billing.domain.billing.paystack_billing.BillingService") as MockService:
        service_instance = MockService.return_value
        service_instance.charge_renewal = AsyncMock(return_value=True)
        
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["amount_billed_usd"] == 29.99
        service_instance.charge_renewal.assert_awaited_once()

@pytest.mark.asyncio
async def test_execute_charge_failed(db):
    handler = RecurringBillingHandler()
    job = BackgroundJob(
        tenant_id=uuid4(),
        payload={"subscription_id": str(uuid4())}
    )
    
    sub = MagicMock(spec=TenantSubscription)
    sub.status = "active"
    
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=sub)))
    
    with patch("app.modules.billing.domain.billing.paystack_billing.BillingService") as MockService:
        service_instance = MockService.return_value
        service_instance.charge_renewal = AsyncMock(return_value=False)
        
        with pytest.raises(Exception) as exc:
            await handler.execute(job, db)
        assert "Paystack charge failed" in str(exc.value)
