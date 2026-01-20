"""
Tests for the Attribution Engine.
BE-FIN-ATTR-1: Validates rule matching and cost allocation logic.
"""
import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock

from app.services.costs.attribution_engine import AttributionEngine
from app.models.attribution import AttributionRule, CostAllocation
from app.models.cloud import CostRecord


@pytest.fixture
def mock_cost_record():
    """Create a mock cost record for testing."""
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.tenant_id = uuid4()
    record.recorded_at = date.today()
    record.amount = Decimal("100.00")
    record.service = "AmazonS3"
    record.region = "us-east-1"
    record.account_id = "123456789012"
    record.tags = {"Team": "Ops", "Environment": "Prod"}
    return record


@pytest.fixture
def mock_rules():
    """Create sample attribution rules."""
    rules = []
    
    # Rule 1: Direct allocation for S3 Ops team
    rule1 = MagicMock(spec=AttributionRule)
    rule1.id = uuid4()
    rule1.name = "S3 Ops Allocation"
    rule1.rule_type = "DIRECT"
    rule1.priority = 10
    rule1.conditions = {"service": "AmazonS3", "tags": {"Team": "Ops"}}
    rule1.allocation = [{"bucket": "Operations Team", "percentage": 100}]
    rules.append(rule1)
    
    # Rule 2: Percentage split for EC2
    rule2 = MagicMock(spec=AttributionRule)
    rule2.id = uuid4()
    rule2.name = "EC2 Split"
    rule2.rule_type = "PERCENTAGE"
    rule2.priority = 20
    rule2.conditions = {"service": "AmazonEC2"}
    rule2.allocation = [
        {"bucket": "Engineering", "percentage": 60},
        {"bucket": "QA", "percentage": 40}
    ]
    rules.append(rule2)
    
    return rules


class TestAttributionEngine:
    """Test suite for AttributionEngine."""

    def test_match_conditions_service(self, mock_cost_record):
        """Test matching by service name."""
        engine = AttributionEngine(AsyncMock())
        
        # Should match
        assert engine.match_conditions(mock_cost_record, {"service": "AmazonS3"}) is True
        
        # Should not match
        assert engine.match_conditions(mock_cost_record, {"service": "AmazonEC2"}) is False

    def test_match_conditions_tags(self, mock_cost_record):
        """Test matching by tags."""
        engine = AttributionEngine(AsyncMock())
        
        # Should match - exact tag
        assert engine.match_conditions(mock_cost_record, {"tags": {"Team": "Ops"}}) is True
        
        # Should match - multiple tags
        assert engine.match_conditions(mock_cost_record, {"tags": {"Team": "Ops", "Environment": "Prod"}}) is True
        
        # Should not match - wrong value
        assert engine.match_conditions(mock_cost_record, {"tags": {"Team": "Dev"}}) is False
        
        # Should not match - missing tag
        assert engine.match_conditions(mock_cost_record, {"tags": {"Project": "Main"}}) is False

    def test_match_conditions_combined(self, mock_cost_record):
        """Test matching with multiple conditions."""
        engine = AttributionEngine(AsyncMock())
        
        # All conditions match
        assert engine.match_conditions(mock_cost_record, {
            "service": "AmazonS3",
            "region": "us-east-1",
            "tags": {"Team": "Ops"}
        }) is True
        
        # One condition fails
        assert engine.match_conditions(mock_cost_record, {
            "service": "AmazonS3",
            "region": "eu-west-1",  # Wrong region
            "tags": {"Team": "Ops"}
        }) is False

    @pytest.mark.asyncio
    async def test_apply_rules_direct_allocation(self, mock_cost_record, mock_rules):
        """Test DIRECT rule type creates single allocation."""
        engine = AttributionEngine(AsyncMock())
        
        allocations = await engine.apply_rules(mock_cost_record, mock_rules)
        
        # Should create exactly 1 allocation (from rule 1)
        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Operations Team"
        assert allocations[0].amount == Decimal("100.00")
        assert allocations[0].percentage == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_apply_rules_percentage_split(self):
        """Test PERCENTAGE rule type creates multiple allocations."""
        engine = AttributionEngine(AsyncMock())
        
        # Create EC2 cost record
        record = MagicMock(spec=CostRecord)
        record.id = uuid4()
        record.recorded_at = date.today()
        record.amount = Decimal("200.00")
        record.service = "AmazonEC2"
        record.region = "us-east-1"
        record.account_id = "123456789012"
        record.tags = {}
        
        # Create percentage rule
        rule = MagicMock(spec=AttributionRule)
        rule.id = uuid4()
        rule.rule_type = "PERCENTAGE"
        rule.conditions = {"service": "AmazonEC2"}
        rule.allocation = [
            {"bucket": "Engineering", "percentage": 60},
            {"bucket": "QA", "percentage": 40}
        ]
        
        allocations = await engine.apply_rules(record, [rule])
        
        # Should create 2 allocations
        assert len(allocations) == 2
        
        # Check amounts
        eng_alloc = next(a for a in allocations if a.allocated_to == "Engineering")
        qa_alloc = next(a for a in allocations if a.allocated_to == "QA")
        
        assert eng_alloc.amount == Decimal("120.00")  # 60% of 200
        assert qa_alloc.amount == Decimal("80.00")    # 40% of 200

    @pytest.mark.asyncio
    async def test_apply_rules_no_match_default_allocation(self):
        """Test that unmatched costs go to 'Unallocated'."""
        engine = AttributionEngine(AsyncMock())
        
        # Create cost record that won't match any rule
        record = MagicMock(spec=CostRecord)
        record.id = uuid4()
        record.recorded_at = date.today()
        record.amount = Decimal("50.00")
        record.service = "AWSLambda"  # No rules for Lambda
        record.region = "us-west-2"
        record.account_id = "111111111111"
        record.tags = {}
        
        # Empty rules list
        allocations = await engine.apply_rules(record, [])
        
        # Should create default allocation
        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Unallocated"
        assert allocations[0].amount == Decimal("50.00")
        assert allocations[0].rule_id is None

    @pytest.mark.asyncio
    async def test_first_matching_rule_wins(self, mock_cost_record):
        """Test that first matching rule (by priority) is applied."""
        engine = AttributionEngine(AsyncMock())
        
        # Create two rules that both match
        rule1 = MagicMock(spec=AttributionRule)
        rule1.id = uuid4()
        rule1.rule_type = "DIRECT"
        rule1.priority = 10
        rule1.conditions = {"service": "AmazonS3"}
        rule1.allocation = [{"bucket": "First", "percentage": 100}]
        
        rule2 = MagicMock(spec=AttributionRule)
        rule2.id = uuid4()
        rule2.rule_type = "DIRECT"
        rule2.priority = 20
        rule2.conditions = {"service": "AmazonS3"}
        rule2.allocation = [{"bucket": "Second", "percentage": 100}]
        
        allocations = await engine.apply_rules(mock_cost_record, [rule1, rule2])
        
        # Only first rule should apply
        assert len(allocations) == 1
        assert allocations[0].allocated_to == "First"
