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
        "baseline_hourly_spend": 1.0, # $1/hr floor
        "average_hourly_spend": 1.5,
        "confidence_score": 0.91,
        "coverage_ratio": 0.95,
        "region": "us-east-1",
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
    assert float(rec.estimated_monthly_savings_low) == 146.0
    assert float(rec.estimated_monthly_savings_high) == 219.0
    assert float(rec.break_even_months) == 0.0
    assert float(rec.confidence_score) == pytest.approx(0.918, rel=1e-6)
    assert rec.term == CommitmentTerm.ONE_YEAR
    assert rec.payment_option == PaymentOption.NO_UPFRONT

@pytest.mark.asyncio
async def test_compute_savings_below_threshold(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    
    # Very low spend should not trigger recommendation
    usage_data = {
        "baseline_hourly_spend": 0.01, 
        "average_hourly_spend": 0.05
    }
    
    recs = await strategy.analyze(uuid4(), usage_data)
    assert len(recs) == 0


def test_compute_savings_backtest_harness(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    # Stable historical load with tiny variance should stay inside tolerance.
    historical = [1.0 + (0.01 if i % 2 == 0 else -0.01) for i in range(240)]

    result = strategy.backtest_hourly_series(historical, tolerance=0.10)

    assert result["sample_size"] == 24
    assert result["within_tolerance"] is True
    assert result["mape"] <= 0.10

def test_calculate_roi_math(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    
    # $100 -> $70 ($30 savings)
    roi = strategy.calculate_roi(100.0, 70.0)
    assert roi == 30.0
    
    roi_zero = strategy.calculate_roi(0.0, 0.0)
    assert roi_zero == 0.0


@pytest.mark.asyncio
async def test_compute_savings_with_upfront_break_even(mock_strategy_config):
    mock_strategy_config.config.update(
        {
            "upfront_cost": 365.0,
            "savings_rate": 0.25,
            "hours_per_month": 730.0,
        }
    )
    strategy = ComputeSavingsStrategy(mock_strategy_config)

    recs = await strategy.analyze(
        uuid4(),
        {
            "baseline_hourly_spend": 1.0,
            "confidence_score": 0.9,
            "coverage_ratio": 0.8,
        },
    )

    assert len(recs) == 1
    rec = recs[0]
    assert float(rec.break_even_months) == pytest.approx(2.0, rel=1e-6)


def test_compute_savings_backtest_insufficient_history(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    result = strategy.backtest_hourly_series([1.0] * 20, tolerance=0.2)

    assert result["within_tolerance"] is False
    assert result["sample_size"] == 0
    assert result["reason"] == "insufficient_history"


def test_compute_savings_backtest_all_zero_history(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)
    result = strategy.backtest_hourly_series([0.0] * 60, tolerance=0.2)

    assert result["within_tolerance"] is True
    assert result["reason"] == "all_zero_history"
    assert result["sample_size"] == 24


def test_compute_savings_percentile_edge_cases(mock_strategy_config):
    strategy = ComputeSavingsStrategy(mock_strategy_config)

    assert strategy._percentile([], 0.25) == 0.0
    assert strategy._percentile([3.5], 0.25) == 3.5
