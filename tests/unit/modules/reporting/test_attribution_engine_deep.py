"""
Comprehensive tests for Attribution Engine module.
Tests cost attribution, rule matching, allocation strategies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
import uuid
from datetime import datetime, timezone

from app.modules.reporting.domain.attribution_engine import AttributionEngine
from app.models.attribution import AttributionRule
from app.models.cloud import CostRecord


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


@pytest.fixture
def attribution_engine(mock_db):
    return AttributionEngine(mock_db)


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def cost_record(tenant_id):
    """Create a sample CostRecord mock."""
    record = MagicMock(spec=CostRecord)
    record.id = uuid.uuid4()
    record.tenant_id = tenant_id
    record.cost_usd = Decimal("100.00")
    record.service = "ec2"
    record.region = "us-east-1"
    record.tags = {"environment": "production", "team": "platform"}
    record.recorded_at = datetime.now(timezone.utc)
    return record


class TestAttributionEngine:
    def test_match_conditions_service(self, attribution_engine, cost_record):
        """Test matching by service."""
        assert (
            attribution_engine.match_conditions(cost_record, {"service": "ec2"}) is True
        )
        assert (
            attribution_engine.match_conditions(cost_record, {"service": "s3"}) is False
        )

    def test_match_conditions_region(self, attribution_engine, cost_record):
        """Test matching by region."""
        assert (
            attribution_engine.match_conditions(cost_record, {"region": "us-east-1"})
            is True
        )
        assert (
            attribution_engine.match_conditions(cost_record, {"region": "eu-west-1"})
            is False
        )

    def test_match_conditions_tags(self, attribution_engine, cost_record):
        """Test matching by tags."""
        assert (
            attribution_engine.match_conditions(
                cost_record, {"tags": {"environment": "production"}}
            )
            is True
        )
        assert (
            attribution_engine.match_conditions(
                cost_record, {"tags": {"team": "platform"}}
            )
            is True
        )
        assert (
            attribution_engine.match_conditions(
                cost_record, {"tags": {"environment": "staging"}}
            )
            is False
        )
        # Multiple tags
        assert (
            attribution_engine.match_conditions(
                cost_record, {"tags": {"environment": "production", "team": "platform"}}
            )
            is True
        )

    @pytest.mark.asyncio
    async def test_apply_rules_direct(self, attribution_engine, cost_record):
        """Test applying a DIRECT allocation rule."""
        rule = AttributionRule(
            id=uuid.uuid4(),
            rule_type="DIRECT",
            conditions={"service": "ec2"},
            allocation={"bucket": "Engineering"},
            priority=1,
        )

        allocations = await attribution_engine.apply_rules(cost_record, [rule])

        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Engineering"
        assert allocations[0].amount == Decimal("100.00")
        assert allocations[0].percentage == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_apply_rules_percentage(self, attribution_engine, cost_record):
        """Test applying a PERCENTAGE allocation rule."""
        rule = AttributionRule(
            id=uuid.uuid4(),
            rule_type="PERCENTAGE",
            conditions={"service": "ec2"},
            allocation=[
                {"bucket": "Frontend", "percentage": 60},
                {"bucket": "Backend", "percentage": 40},
            ],
            priority=1,
        )

        allocations = await attribution_engine.apply_rules(cost_record, [rule])

        assert len(allocations) == 2

        frontend = next(a for a in allocations if a.allocated_to == "Frontend")
        assert frontend.amount == Decimal("60.00")
        assert frontend.percentage == Decimal("60")

        backend = next(a for a in allocations if a.allocated_to == "Backend")
        assert backend.amount == Decimal("40.00")
        assert backend.percentage == Decimal("40")

    @pytest.mark.asyncio
    async def test_apply_rules_fixed(self, attribution_engine, cost_record):
        """Test applying a FIXED allocation rule."""
        rule = AttributionRule(
            id=uuid.uuid4(),
            rule_type="FIXED",
            conditions={"service": "ec2"},
            allocation={"bucket": "Shared", "amount": 20.00},
            priority=1,
        )

        allocations = await attribution_engine.apply_rules(cost_record, [rule])

        assert len(allocations) == 2  # Fixed + Remaining

        shared = next(a for a in allocations if a.allocated_to == "Shared")
        assert shared.amount == Decimal("20.00")

        unallocated = next(a for a in allocations if a.allocated_to == "Unallocated")
        assert unallocated.amount == Decimal("80.00")  # 100 - 20

    @pytest.mark.asyncio
    async def test_apply_rules_no_match_default(self, attribution_engine, cost_record):
        """Test mismatch results in default Unallocated."""
        rule = AttributionRule(
            id=uuid.uuid4(),
            rule_type="DIRECT",
            conditions={"service": "s3"},  # Mismatch
            allocation={"bucket": "Storage"},
            priority=1,
        )

        allocations = await attribution_engine.apply_rules(cost_record, [rule])

        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Unallocated"
        assert allocations[0].amount == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_process_cost_record_flow(
        self, attribution_engine, mock_db, tenant_id, cost_record
    ):
        """Test full process_cost_record flow."""
        # Mock get_active_rules
        rule = AttributionRule(
            id=uuid.uuid4(),
            rule_type="DIRECT",
            conditions={"service": "ec2"},
            allocation={"bucket": "Engineering"},
            priority=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule]
        mock_db.execute.return_value = mock_result

        allocations = await attribution_engine.process_cost_record(
            cost_record, tenant_id
        )

        assert len(allocations) == 1
        assert allocations[0].allocated_to == "Engineering"
        # Verify persistence
        assert mock_db.add.called
        assert mock_db.commit.called
