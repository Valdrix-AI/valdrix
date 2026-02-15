import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.reporting.domain.attribution_engine import AttributionEngine
from app.models.attribution import AttributionRule
from app.models.cloud import CostRecord


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def engine(mock_db):
    return AttributionEngine(mock_db)


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.mark.asyncio
async def test_get_active_rules(mock_db, engine, tenant_id):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    rules = await engine.get_active_rules(tenant_id)
    assert isinstance(rules, list)
    mock_db.execute.assert_called_once()


def test_match_conditions_service(engine):
    record = MagicMock(spec=CostRecord)
    record.service = "S3"

    assert engine.match_conditions(record, {"service": "S3"}) is True
    assert engine.match_conditions(record, {"service": "EC2"}) is False


def test_match_conditions_tags(engine):
    record = MagicMock(spec=CostRecord)
    record.tags = {"Team": "Alpha", "Env": "Prod"}

    assert engine.match_conditions(record, {"tags": {"Team": "Alpha"}}) is True
    assert engine.match_conditions(record, {"tags": {"Team": "Beta"}}) is False
    assert (
        engine.match_conditions(record, {"tags": {"Team": "Alpha", "Env": "Prod"}})
        is True
    )


@pytest.mark.asyncio
async def test_apply_rules_direct(engine):
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.cost_usd = Decimal("100.00")
    record.recorded_at = date(2026, 1, 1)

    rule = MagicMock(spec=AttributionRule)
    rule.id = uuid4()
    rule.rule_type = "DIRECT"
    rule.conditions = {"service": "S3"}
    rule.allocation = {"bucket": "Team-A"}

    # Mock match_conditions because we are testing apply_rules logic
    with patch.object(engine, "match_conditions", return_value=True):
        allocs = await engine.apply_rules(record, [rule])

    assert len(allocs) == 1
    assert allocs[0].allocated_to == "Team-A"
    assert allocs[0].amount == Decimal("100.00")


@pytest.mark.asyncio
async def test_apply_rules_percentage(engine):
    record = MagicMock(spec=CostRecord)
    record.cost_usd = Decimal("100.00")

    rule = MagicMock(spec=AttributionRule)
    rule.rule_type = "PERCENTAGE"
    rule.allocation = [
        {"bucket": "Team-A", "percentage": 60},
        {"bucket": "Team-B", "percentage": 40},
    ]

    with patch.object(engine, "match_conditions", return_value=True):
        allocs = await engine.apply_rules(record, [rule])

    assert len(allocs) == 2
    allocs.sort(key=lambda x: x.allocated_to)
    assert allocs[0].amount == Decimal("60.00")
    assert allocs[1].amount == Decimal("40.00")


@pytest.mark.asyncio
async def test_apply_rules_fixed(engine):
    record = MagicMock(spec=CostRecord)
    record.cost_usd = Decimal("100.00")

    rule = MagicMock(spec=AttributionRule)
    rule.rule_type = "FIXED"
    rule.allocation = [
        {"bucket": "License-Fee", "amount": 10},
    ]

    with patch.object(engine, "match_conditions", return_value=True):
        allocs = await engine.apply_rules(record, [rule])

    assert len(allocs) == 2  # Fixed + Unallocated remainder
    assert any(
        a.allocated_to == "License-Fee" and a.amount == Decimal("10") for a in allocs
    )
    assert any(
        a.allocated_to == "Unallocated" and a.amount == Decimal("90") for a in allocs
    )


@pytest.mark.asyncio
async def test_apply_rules_no_match(engine):
    record = MagicMock(spec=CostRecord)
    record.cost_usd = Decimal("10.00")

    allocs = await engine.apply_rules(record, [])

    assert len(allocs) == 1
    assert allocs[0].allocated_to == "Unallocated"
    assert allocs[0].amount == Decimal("10.00")


@pytest.mark.asyncio
async def test_process_cost_record(mock_db, engine, tenant_id):
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.cost_usd = Decimal("50.00")

    with patch.object(engine, "get_active_rules", return_value=[]):
        allocs = await engine.process_cost_record(record, tenant_id)

    assert len(allocs) == 1
    mock_db.add.assert_called()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_apply_rules_to_tenant(mock_db, engine, tenant_id):
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record]
    mock_db.execute.return_value = mock_result

    with patch.object(engine, "get_active_rules", return_value=[]):
        await engine.apply_rules_to_tenant(
            tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )

    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_get_allocation_summary(mock_db, engine, tenant_id):
    row = MagicMock()
    row.allocated_to = "Team-A"
    row.total_amount = Decimal("100.00")
    row.record_count = 10

    mock_result = MagicMock()
    mock_result.all.return_value = [row]
    mock_db.execute.return_value = mock_result

    summary = await engine.get_allocation_summary(tenant_id)
    assert summary["total"] == 100.0
    assert summary["buckets"][0]["name"] == "Team-A"


@pytest.mark.asyncio
async def test_get_unallocated_analysis(mock_db, engine, tenant_id):
    row = MagicMock()
    row.service = "EC2"
    row.total_unallocated = Decimal("50.00")
    row.record_count = 5

    mock_result = MagicMock()
    mock_result.all.return_value = [row]
    mock_db.execute.return_value = mock_result

    res = await engine.get_unallocated_analysis(
        tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert len(res) == 1
    assert res[0]["service"] == "EC2"
    assert "recommendation" in res[0]


def test_validate_rule_payload_invalid_types(engine):
    errors = engine.validate_rule_payload("unknown", {"bucket": "A"})
    assert errors
    assert "rule_type must be one of" in errors[0]


def test_validate_rule_payload_percentage_and_fixed_rules(engine):
    percentage_errors = engine.validate_rule_payload(
        "PERCENTAGE",
        [{"bucket": "A", "percentage": 70}, {"bucket": "B", "percentage": 20}],
    )
    fixed_errors = engine.validate_rule_payload(
        "FIXED",
        [{"bucket": "A", "amount": -1}],
    )
    assert "sum to 100" in " ".join(percentage_errors)
    assert "cannot be negative" in " ".join(fixed_errors)


def test_allocation_entries_normalization(engine):
    assert engine._allocation_entries({"bucket": "A"}) == [{"bucket": "A"}]
    assert engine._allocation_entries([{"bucket": "A"}, 1, "x"]) == [{"bucket": "A"}]
    assert engine._allocation_entries("bad") == []


@pytest.mark.asyncio
async def test_update_and_delete_rule_not_found_paths(engine, tenant_id):
    with patch.object(engine, "get_rule", new=AsyncMock(return_value=None)):
        result = await engine.update_rule(tenant_id, uuid4(), {"name": "x"})
        deleted = await engine.delete_rule(tenant_id, uuid4())
    assert result is None
    assert deleted is False


@pytest.mark.asyncio
async def test_update_rule_normalizes_type(mock_db, engine, tenant_id):
    rule = MagicMock(spec=AttributionRule)
    rule.id = uuid4()
    rule.rule_type = "DIRECT"
    with patch.object(engine, "get_rule", new=AsyncMock(return_value=rule)):
        updated = await engine.update_rule(
            tenant_id,
            rule.id,
            {
                "rule_type": "percentage",
                "name": "Updated",
                "allocation": {"bucket": "Ops"},
            },
        )
    assert updated is rule
    assert rule.rule_type == "PERCENTAGE"
    mock_db.commit.assert_awaited()
    mock_db.refresh.assert_awaited_with(rule)


@pytest.mark.asyncio
async def test_apply_rules_percentage_mismatch_logs_warning(engine):
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.cost_usd = Decimal("100.00")
    record.recorded_at = date(2026, 1, 1)
    rule = MagicMock(spec=AttributionRule)
    rule.id = uuid4()
    rule.rule_type = "PERCENTAGE"
    rule.conditions = {}
    rule.allocation = [{"bucket": "A", "percentage": 10}]
    with (
        patch.object(engine, "match_conditions", return_value=True),
        patch(
            "app.modules.reporting.domain.attribution_engine.logger.warning"
        ) as mock_warning,
    ):
        allocations = await engine.apply_rules(record, [rule])
    assert len(allocations) == 1
    mock_warning.assert_called_once()


@pytest.mark.asyncio
async def test_apply_rules_fixed_without_remaining(engine):
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.cost_usd = Decimal("10.00")
    record.recorded_at = date(2026, 1, 1)
    rule = MagicMock(spec=AttributionRule)
    rule.id = uuid4()
    rule.rule_type = "FIXED"
    rule.conditions = {}
    rule.allocation = [{"bucket": "A", "amount": 10}]
    with patch.object(engine, "match_conditions", return_value=True):
        allocations = await engine.apply_rules(record, [rule])
    assert len(allocations) == 1
    assert allocations[0].allocated_to == "A"


@pytest.mark.asyncio
async def test_apply_rules_to_tenant_no_records_logs_and_returns_zero(
    mock_db, engine, tenant_id
):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result
    with patch(
        "app.modules.reporting.domain.attribution_engine.logger.info"
    ) as mock_info:
        result = await engine.apply_rules_to_tenant(
            tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )
    assert result == {"records_processed": 0, "allocations_created": 0}
    mock_info.assert_called_once()


@pytest.mark.asyncio
async def test_get_allocation_summary_with_date_filters(mock_db, engine, tenant_id):
    row = MagicMock()
    row.allocated_to = "Ops"
    row.total_amount = Decimal("25.50")
    row.record_count = 2
    mock_result = MagicMock()
    mock_result.all.return_value = [row]
    mock_db.execute.return_value = mock_result

    summary = await engine.get_allocation_summary(
        tenant_id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        bucket="Ops",
    )
    assert summary["total"] == 25.5
    assert summary["buckets"][0]["name"] == "Ops"


@pytest.mark.asyncio
async def test_simulate_rule_handles_empty_sample(mock_db, engine, tenant_id):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    result = await engine.simulate_rule(
        tenant_id,
        rule_type="DIRECT",
        conditions={},
        allocation={"bucket": "Ops"},
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        sample_limit=10,
    )
    assert result["sampled_records"] == 0
    assert result["matched_records"] == 0
    assert result["match_rate"] == 0.0
    assert result["projected_allocations"] == []
