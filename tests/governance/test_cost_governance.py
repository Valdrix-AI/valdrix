
import pytest
from uuid import uuid4
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock
from app.modules.reporting.domain.aggregator import CostAggregator

@pytest.mark.asyncio
async def test_get_governance_report():
    """Test that governance report correctly calculates percentages and warnings."""
    tenant_id = uuid4()
    db = AsyncMock()
    
    # 1. Mock total cost query
    total_result = MagicMock()
    total_result.scalar.return_value = Decimal("1000.00")
    
    # 2. Mock untagged cost query
    untagged_result = MagicMock()
    untagged_row = MagicMock()
    untagged_row.total_untagged_cost = Decimal("150.00") # 15% (should trigger warning)
    untagged_row.untagged_count = 10
    untagged_result.one.return_value = untagged_row
    
    # 3. Mock unallocated analysis query
    unallocated_result = MagicMock()
    unallocated_result.all.return_value = []
    
    # Setting up the side effects for the multiple execute calls
    db.execute.side_effect = [total_result, untagged_result, unallocated_result]
    
    report = await CostAggregator.get_governance_report(
        db, tenant_id, date(2025, 1, 1), date(2025, 1, 31)
    )
    
    assert report["total_cost"] == 1000.0
    assert report["unallocated_cost"] == 150.0
    assert report["unallocated_percentage"] == 15.0
    assert report["status"] == "warning"
    assert "High unallocated spend detected" in report["recommendation"]

@pytest.mark.asyncio
async def test_get_governance_report_healthy():
    """Test governance report with low untagged costs."""
    tenant_id = uuid4()
    db = AsyncMock()
    
    # 1. Mock total cost query
    total_result = MagicMock()
    total_result.scalar.return_value = Decimal("1000.00")
    
    # 2. Mock untagged cost query
    untagged_result = MagicMock()
    untagged_row = MagicMock()
    untagged_row.total_untagged_cost = Decimal("50.00") # 5% (healthy)
    untagged_row.untagged_count = 5
    untagged_result.one.return_value = untagged_row
    
    # 3. Mock unallocated analysis query
    unallocated_result = MagicMock()
    unallocated_result.all.return_value = []
    
    db.execute.side_effect = [total_result, untagged_result, unallocated_result]
    
    report = await CostAggregator.get_governance_report(
        db, tenant_id, date(2025, 1, 1), date(2025, 1, 31)
    )
    
    assert report["unallocated_percentage"] == 5.0
    assert report["status"] == "healthy"
    assert report["recommendation"] is None
