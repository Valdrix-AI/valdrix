"""
Tests for Delta Analysis Service

Covers:
- CostDelta classification
- DeltaAnalysisResult generation
- Delta computation from cost data
- LLM prompt optimization
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from uuid import uuid4

from app.shared.llm.delta_analysis import (
    CostDelta,
    DeltaAnalysisResult,
    DeltaAnalysisService,
    analyze_with_delta
)


class TestCostDelta:
    """Tests for CostDelta dataclass."""
    
    def test_is_significant_above_threshold(self):
        """Changes above threshold should be significant."""
        delta = CostDelta(
            resource_id="ec2-123",
            resource_type="EC2",
            previous_cost=100.0,
            current_cost=120.0,
            change_amount=20.0,
            change_percent=20.0  # Above 15% threshold
        )
        assert delta.is_significant is True
    
    def test_is_significant_below_threshold(self):
        """Changes below threshold should not be significant."""
        delta = CostDelta(
            resource_id="ec2-123",
            resource_type="EC2",
            previous_cost=100.0,
            current_cost=105.0,
            change_amount=5.0,
            change_percent=5.0  # Below 15% threshold
        )
        assert delta.is_significant is False
    
    def test_is_spike_over_50_percent(self):
        """Increases over 50% should be spikes."""
        delta = CostDelta(
            resource_id="rds-123",
            resource_type="RDS",
            previous_cost=50.0,
            current_cost=100.0,
            change_amount=50.0,
            change_percent=100.0
        )
        assert delta.is_spike is True
        assert delta.is_drop is False
    
    def test_is_drop_over_30_percent(self):
        """Decreases over 30% should be drops."""
        delta = CostDelta(
            resource_id="elb-123",
            resource_type="ELB",
            previous_cost=100.0,
            current_cost=50.0,
            change_amount=-50.0,
            change_percent=-50.0
        )
        assert delta.is_drop is True
        assert delta.is_spike is False


class TestDeltaAnalysisResult:
    """Tests for DeltaAnalysisResult."""
    
    def test_has_significant_changes_with_increases(self):
        """Should detect significant changes when increases exist."""
        result = DeltaAnalysisResult(
            tenant_id=uuid4(),
            analysis_date=date.today(),
            top_increases=[
                CostDelta("ec2-1", "EC2", 100, 130, 30, 30)
            ]
        )
        assert result.has_significant_changes is True
    
    def test_has_significant_changes_with_new_resources(self):
        """Should detect significant changes with new resources."""
        result = DeltaAnalysisResult(
            tenant_id=uuid4(),
            analysis_date=date.today(),
            new_resources=[{"resource": "newdb", "type": "RDS"}]
        )
        assert result.has_significant_changes is True
    
    def test_no_significant_changes(self):
        """Should return False when no significant changes."""
        result = DeltaAnalysisResult(
            tenant_id=uuid4(),
            analysis_date=date.today(),
            total_change_percent=2.0  # Small change
        )
        assert result.has_significant_changes is False
    
    def test_as_llm_prompt_data_is_compact(self):
        """LLM prompt data should be compact (few fields)."""
        result = DeltaAnalysisResult(
            tenant_id=uuid4(),
            analysis_date=date.today(),
            total_previous=1000.0,
            total_current=1150.0,
            total_change=150.0,
            total_change_percent=15.0,
            significant_changes_count=3
        )
        
        prompt_data = result.as_llm_prompt_data()
        
        assert "summary" in prompt_data
        assert "top_cost_increases" in prompt_data
        assert "instructions" in prompt_data
        assert prompt_data["analysis_type"] == "delta"
    
    def test_as_json_serializes(self):
        """Should serialize to valid JSON."""
        result = DeltaAnalysisResult(
            tenant_id=uuid4(),
            analysis_date=date.today()
        )
        
        json_str = result.as_json()
        import json
        parsed = json.loads(json_str)
        
        assert isinstance(parsed, dict)
        assert "analysis_type" in parsed


class TestDeltaAnalysisService:
    """Tests for DeltaAnalysisService."""
    
    @pytest.mark.asyncio
    async def test_compute_delta_with_increases(self):
        """Should detect cost increases."""
        service = DeltaAnalysisService()
        
        current = [
            {
                "TimePeriod": {"Start": "2026-01-13"},
                "Groups": [
                    {"Keys": ["EC2", "i-123"], "Metrics": {"UnblendedCost": {"Amount": "150"}}}
                ]
            }
        ]
        previous = [
            {
                "TimePeriod": {"Start": "2026-01-10"},
                "Groups": [
                    {"Keys": ["EC2", "i-123"], "Metrics": {"UnblendedCost": {"Amount": "100"}}}
                ]
            }
        ]
        
        result = await service.compute_delta(
            tenant_id=uuid4(),
            current_costs=current,
            previous_costs=previous
        )
        
        assert result.total_change > 0
        assert len(result.top_increases) > 0
    
    @pytest.mark.asyncio
    async def test_compute_delta_detects_new_resources(self):
        """Should detect new resources."""
        service = DeltaAnalysisService()
        
        current = [
            {
                "TimePeriod": {"Start": "2026-01-13"},
                "Groups": [
                    {"Keys": ["RDS", "newdb"], "Metrics": {"UnblendedCost": {"Amount": "50"}}}
                ]
            }
        ]
        previous = []
        
        result = await service.compute_delta(
            tenant_id=uuid4(),
            current_costs=current,
            previous_costs=previous
        )
        
        assert len(result.new_resources) > 0
        assert result.new_resources[0]["resource"] == "newdb"
    
    @pytest.mark.asyncio
    async def test_compute_delta_filters_small_changes(self):
        """Should filter out small changes."""
        service = DeltaAnalysisService()
        
        current = [
            {
                "TimePeriod": {"Start": "2026-01-13"},
                "Groups": [
                    {"Keys": ["S3", "bucket"], "Metrics": {"UnblendedCost": {"Amount": "10.10"}}}
                ]
            }
        ]
        previous = [
            {
                "TimePeriod": {"Start": "2026-01-10"},
                "Groups": [
                    {"Keys": ["S3", "bucket"], "Metrics": {"UnblendedCost": {"Amount": "10.00"}}}
                ]
            }
        ]
        
        result = await service.compute_delta(
            tenant_id=uuid4(),
            current_costs=current,
            previous_costs=previous
        )
        
        # $0.10 change should not appear in top increases
        assert len(result.top_increases) == 0


class TestAnalyzeWithDelta:
    """Tests for analyze_with_delta convenience function."""
    
    @pytest.mark.asyncio
    async def test_returns_cached_result_when_available(self):
        """Should return cached result if available."""
        tenant_id = uuid4()
        cached_result = {"status": "cached", "anomalies": []}
        
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value=cached_result)
        
        with patch('app.shared.llm.delta_analysis.get_cache_service', return_value=mock_cache):
            mock_analyzer = AsyncMock()
            
            result = await analyze_with_delta(
                analyzer=mock_analyzer,
                tenant_id=tenant_id,
                current_costs=[]
            )
        
        import json
        parsed = json.loads(result)
        assert parsed["status"] == "cached"
    
    @pytest.mark.asyncio
    async def test_returns_no_changes_when_stable(self):
        """Should return simple response when no significant changes."""
        tenant_id = uuid4()
        
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value=None)
        mock_cache.set_analysis = AsyncMock()
        
        with patch('app.shared.llm.delta_analysis.get_cache_service', return_value=mock_cache):
            mock_analyzer = AsyncMock()
            
            # Empty costs = no changes
            result = await analyze_with_delta(
                analyzer=mock_analyzer,
                tenant_id=tenant_id,
                current_costs=[],
                previous_costs=[]
            )
        
        import json
        parsed = json.loads(result)
        assert parsed["status"] == "no_significant_changes"
        # LLM should NOT be called
        mock_analyzer.analyze.assert_not_called()
