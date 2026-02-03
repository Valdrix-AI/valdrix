import pytest
from uuid import uuid4

from app.modules.optimization.domain.strategies.compute_savings import ComputeSavingsStrategy
from app.models.optimization import OptimizationStrategy, CommitmentTerm, PaymentOption

@pytest.fixture
def mock_strategy_config():
    return OptimizationStrategy(
        id=uuid4(),
        name="AWS Compute SP",
        type="savings_plan",
        provider="aws",
        config={"savings_rate": 0.25}
    )

@pytest.mark.asyncio
async def test_compute_savings_analysis_basic(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    
    usage_data = {
        "min_hourly_spend": 1.0, # $1/hr floor
        "average_hourly_spend": 1.5,
        "region": "us-east-1"
    }
    
    tenant_id = uuid4()
    recs = await strategy.analyze(tenant_id, usage_data)
    
    assert len(recs) == 1
    rec = recs[0]
    assert rec.tenant_id == tenant_id
    assert rec.resource_type == "Compute Savings Plan"
    assert rec.roi_percentage == 25.0
    # $1/hr * 730 * 0.25 = $182.5 savings
    assert float(rec.estimated_monthly_savings) == 182.5
    assert rec.term == CommitmentTerm.ONE_YEAR
    assert rec.payment_option == PaymentOption.NO_UPFRONT

@pytest.mark.asyncio
async def test_compute_savings_below_threshold(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    
    # Very low spend should not trigger recommendation
    usage_data = {
        "min_hourly_spend": 0.01, 
        "average_hourly_spend": 0.05
    }
    
    recs = await strategy.analyze(uuid4(), usage_data)
    assert len(recs) == 0

def test_calculate_roi_math(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    
    # $100 -> $70 ($30 savings)
    roi = strategy.calculate_roi(100.0, 70.0)
    assert roi == 30.0
    
    roi_zero = strategy.calculate_roi(0.0, 0.0)
    assert roi_zero == 0.0
