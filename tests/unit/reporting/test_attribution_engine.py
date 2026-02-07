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
    assert engine.match_conditions(record, {"tags": {"Team": "Alpha", "Env": "Prod"}}) is True

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
        {"bucket": "Team-B", "percentage": 40}
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
        
    assert len(allocs) == 2 # Fixed + Unallocated remainder
    assert any(a.allocated_to == "License-Fee" and a.amount == Decimal("10") for a in allocs)
    assert any(a.allocated_to == "Unallocated" and a.amount == Decimal("90") for a in allocs)

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
        await engine.apply_rules_to_tenant(tenant_id, date(2026, 1, 1), date(2026, 1, 31))
        
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
    
    res = await engine.get_unallocated_analysis(tenant_id, date(2026, 1, 1), date(2026, 1, 31))
    assert len(res) == 1
    assert res[0]["service"] == "EC2"
    assert "recommendation" in res[0]
