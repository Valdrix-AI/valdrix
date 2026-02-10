import pytest
from typing import Dict
from unittest.mock import MagicMock
from uuid import uuid4
from app.shared.llm.delta_analysis import DeltaAnalysisService, CostDelta

@pytest.fixture
def delta_service():
    return DeltaAnalysisService(cache=MagicMock())

def test_cost_delta_properties():
    """Test CostDelta logic."""
    # Significant change
    significant = CostDelta("id", "type", 10.0, 20.0, 10.0, 100.0)
    assert significant.is_significant
    assert significant.is_spike
    assert not significant.is_drop
    
    # Drop
    drop = CostDelta("id", "type", 100.0, 10.0, -90.0, -90.0)
    assert drop.is_significant
    assert drop.is_drop
    assert not drop.is_spike
    
    # Insignificant
    minimal = CostDelta("id", "type", 100.0, 101.0, 1.0, 1.0)
    assert not minimal.is_significant

def test_aggregate_by_resource(delta_service):
    """Test aggregating AWS cost data."""
    raw_costs = [
        {
            "Groups": [
                {
                    "Keys": ["AmazonEC2", "i-123"],
                    "Metrics": {"UnblendedCost": {"Amount": "10.0"}}
                },
                {
                    "Keys": ["AmazonRDS", "db-456"],
                    "Metrics": {"UnblendedCost": {"Amount": "20.0"}}
                }
            ]
        },
        {
            "Groups": [
                {
                    "Keys": ["AmazonEC2", "i-123"],
                    "Metrics": {"UnblendedCost": {"Amount": "10.0"}} # Constant
                },
                {
                    "Keys": ["AmazonRDS", "db-456"],
                    "Metrics": {"UnblendedCost": {"Amount": "40.0"}} # Increase
                }
            ]
        }
    ]
    
    aggregated = delta_service._aggregate_by_resource(raw_costs, days=2)
    
    assert "i-123" in aggregated
    assert aggregated["i-123"]["total_cost"] == 20.0
    assert aggregated["i-123"]["daily_cost"] == 10.0
    
    assert "db-456" in aggregated
    assert aggregated["db-456"]["total_cost"] == 60.0
    assert aggregated["db-456"]["daily_cost"] == 30.0

@pytest.mark.asyncio
async def test_compute_delta(delta_service):
    """Test full delta computation."""
    # Previous: average 10.0
    prev_costs = [{"Groups": [{"Keys": ["Service", "r-1"], "Metrics": {"UnblendedCost": {"Amount": "10.0"}}}]}]
    # Current: average 20.0
    curr_costs = [{"Groups": [{"Keys": ["Service", "r-1"], "Metrics": {"UnblendedCost": {"Amount": "20.0"}}}]}]
    
    result = await delta_service.compute_delta(
        tenant_id=uuid4(),
        current_costs=curr_costs,
        previous_costs=prev_costs,
        days_to_compare=1
    )
    
    assert result.total_change == 10.0
    assert result.total_change_percent == 100.0
    assert len(result.top_increases) == 1
    assert result.top_increases[0].resource_id == "r-1"
    assert result.has_significant_changes
