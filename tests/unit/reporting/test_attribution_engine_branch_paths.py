from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.attribution import AttributionRule
from app.models.cloud import CostRecord
from app.modules.reporting.domain.attribution_engine import AttributionEngine


@pytest.fixture
def db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def engine(db: AsyncMock) -> AttributionEngine:
    return AttributionEngine(db)


def test_validate_rule_payload_exhaustive_errors(engine: AttributionEngine) -> None:
    direct_errors = engine.validate_rule_payload("DIRECT", [])
    pct_errors = engine.validate_rule_payload("PERCENTAGE", [{"bucket": "", "percentage": "x"}])
    fixed_errors = engine.validate_rule_payload("FIXED", [{"bucket": "", "amount": "x"}])
    assert "exactly one bucket" in " ".join(direct_errors)
    assert "non-empty 'bucket'" in " ".join(pct_errors)
    assert "numeric 'percentage'" in " ".join(pct_errors)
    assert "numeric 'amount'" in " ".join(fixed_errors)


@pytest.mark.asyncio
async def test_list_get_create_delete_rule_paths(engine: AttributionEngine, db: AsyncMock) -> None:
    tenant_id = uuid4()
    rule_id = uuid4()
    fake_rule = MagicMock(spec=AttributionRule)
    fake_rule.id = rule_id

    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.return_value = [fake_rule]
    scalar_result.scalar_one_or_none.return_value = fake_rule
    db.execute.return_value = scalar_result

    listed = await engine.list_rules(tenant_id, include_inactive=True)
    got = await engine.get_rule(tenant_id, rule_id)
    created = await engine.create_rule(
        tenant_id,
        name="rule",
        priority=1,
        rule_type="direct",
        conditions={},
        allocation={"bucket": "Ops"},
    )
    deleted = await engine.delete_rule(tenant_id, rule_id)

    assert listed == [fake_rule]
    assert got == fake_rule
    assert created.rule_type == "DIRECT"
    assert deleted is True


def test_match_conditions_falls_back_to_ingestion_metadata_tags(engine: AttributionEngine) -> None:
    record = MagicMock(spec=CostRecord)
    record.service = "S3"
    record.region = "us-east-1"
    record.account_id = "123"
    record.tags = None
    record.ingestion_metadata = {"tags": {"Team": "Ops"}}
    assert engine.match_conditions(record, {"tags": {"Team": "Ops"}}) is True
    assert engine.match_conditions(record, {"account_id": "999"}) is False


@pytest.mark.asyncio
async def test_apply_rules_allocation_fallback_variants(engine: AttributionEngine) -> None:
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.recorded_at = date(2026, 1, 1)
    record.cost_usd = Decimal("100")
    record.service = "S3"
    record.region = "us-east-1"
    record.account_id = "123"
    record.ingestion_metadata = {}

    direct = MagicMock(spec=AttributionRule)
    direct.id = uuid4()
    direct.rule_type = "DIRECT"
    direct.conditions = {}
    direct.allocation = "bad-shape"

    percentage = MagicMock(spec=AttributionRule)
    percentage.id = uuid4()
    percentage.rule_type = "PERCENTAGE"
    percentage.conditions = {}
    percentage.allocation = {"bucket": "Eng", "percentage": 100}

    fixed = MagicMock(spec=AttributionRule)
    fixed.id = uuid4()
    fixed.rule_type = "FIXED"
    fixed.conditions = {}
    fixed.allocation = {"bucket": "Shared", "amount": 10}

    with patch.object(engine, "match_conditions", return_value=True):
        direct_allocs = await engine.apply_rules(record, [direct])
        pct_allocs = await engine.apply_rules(record, [percentage])
        fixed_allocs = await engine.apply_rules(record, [fixed])

    assert direct_allocs[0].allocated_to == "Unallocated"
    assert pct_allocs[0].allocated_to == "Eng"
    assert any(a.allocated_to == "Unallocated" for a in fixed_allocs)


@pytest.mark.asyncio
async def test_simulate_rule_projects_allocations(engine: AttributionEngine, db: AsyncMock) -> None:
    tenant_id = uuid4()
    record = MagicMock(spec=CostRecord)
    record.id = uuid4()
    record.tenant_id = tenant_id
    record.cost_usd = Decimal("25")
    record.recorded_at = datetime.now(timezone.utc)
    record.service = "S3"
    record.region = "us-east-1"
    record.account_id = "123"
    record.ingestion_metadata = {}

    result = MagicMock()
    result.scalars.return_value.all.return_value = [record]
    db.execute.return_value = result

    simulation = await engine.simulate_rule(
        tenant_id,
        rule_type="DIRECT",
        conditions={},
        allocation={"bucket": "Ops"},
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        sample_limit=10,
    )

    assert simulation["matched_records"] == 1
    assert simulation["projected_allocation_total"] == 25.0
    assert simulation["projected_allocations"][0]["bucket"] == "Ops"


@pytest.mark.asyncio
async def test_apply_rules_to_tenant_no_records_and_summary_filters(engine: AttributionEngine, db: AsyncMock) -> None:
    tenant_id = uuid4()
    empty_exec = MagicMock()
    empty_exec.scalars.return_value.all.return_value = []
    db.execute.return_value = empty_exec

    no_records = await engine.apply_rules_to_tenant(tenant_id, date(2026, 1, 1), date(2026, 1, 2))
    assert no_records == {"records_processed": 0, "allocations_created": 0}

    summary_exec = MagicMock()
    summary_exec.all.return_value = [SimpleNamespace(allocated_to="Ops", total_amount=Decimal("12"), record_count=2)]
    db.execute.return_value = summary_exec
    summary = await engine.get_allocation_summary(
        tenant_id,
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
        bucket="Ops",
    )
    assert summary["total"] == 12.0
