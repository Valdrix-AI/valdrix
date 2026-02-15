import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.reporting.domain.aggregator import CostAggregator
from app.models.cloud import CostRecord


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    # Mock bind and dialect for statement timeout logic
    db.bind = MagicMock()
    db.bind.dialect = MagicMock()
    db.bind.dialect.name = "sqlite"
    return db


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.mark.asyncio
async def test_count_records(mock_db, tenant_id):
    mock_result = MagicMock()
    mock_result.scalar.return_value = 10
    mock_db.execute.return_value = mock_result

    count = await CostAggregator.count_records(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert count == 10


@pytest.mark.asyncio
async def test_get_data_freshness_no_data(mock_db, tenant_id):
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = MagicMock(total_records=0)
    mock_db.execute.return_value = mock_result

    res = await CostAggregator.get_data_freshness(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["status"] == "no_data"


@pytest.mark.asyncio
async def test_get_data_freshness_mixed(mock_db, tenant_id):
    row = MagicMock()
    row.total_records = 100
    row.preliminary_count = 10
    row.final_count = 90
    row.latest_record_date = date(2026, 1, 31)

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row
    mock_db.execute.return_value = mock_result

    res = await CostAggregator.get_data_freshness(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["status"] == "mixed"


@pytest.mark.asyncio
async def test_get_data_freshness_final_status(mock_db, tenant_id):
    row = MagicMock()
    row.total_records = 10
    row.preliminary_count = 0
    row.final_count = 10
    row.latest_record_date = date(2026, 1, 31)

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row
    mock_db.execute.return_value = mock_result

    res = await CostAggregator.get_data_freshness(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["status"] == "final"


@pytest.mark.asyncio
async def test_get_data_freshness_preliminary_status(mock_db, tenant_id):
    row = MagicMock()
    row.total_records = 10
    row.preliminary_count = 6
    row.final_count = 4
    row.latest_record_date = date(2026, 1, 31)

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row
    mock_db.execute.return_value = mock_result

    res = await CostAggregator.get_data_freshness(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["status"] == "preliminary"


@pytest.mark.asyncio
async def test_get_summary(mock_db, tenant_id):
    r1 = MagicMock(spec=CostRecord)
    r1.cost_usd = Decimal("10.50")
    r1.service = "S3"
    r1.recorded_at = date(2026, 1, 1)
    r1.region = "us-east-1"

    mock_result = MagicMock()
    mock_result.one.return_value = MagicMock(total_cost=Decimal("10.50"), total_count=1)
    mock_result.scalars.return_value.all.return_value = [r1]
    mock_db.execute.return_value = mock_result

    summary = await CostAggregator.get_summary(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert summary.total_cost == Decimal("10.50")


@pytest.mark.asyncio
async def test_get_summary_with_provider_filter(mock_db, tenant_id):
    record = MagicMock(spec=CostRecord)
    record.cost_usd = Decimal("7.50")
    record.service = "EC2"
    record.recorded_at = date(2026, 1, 1)
    record.region = "us-east-1"

    total_result = MagicMock()
    total_result.one.return_value = MagicMock(total_cost=Decimal("7.50"), total_count=1)
    detail_result = MagicMock()
    detail_result.scalars.return_value.all.return_value = [record]
    mock_db.execute.side_effect = [total_result, detail_result]

    summary = await CostAggregator.get_summary(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31), provider="aws"
    )
    assert summary.provider == "aws"


@pytest.mark.asyncio
async def test_get_dashboard_summary(mock_db, tenant_id):
    row = MagicMock()
    row.total_cost = Decimal("100.00")
    row.total_carbon = Decimal("5.00")

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row
    mock_db.execute.return_value = mock_result

    breakdown_data = {
        "breakdown": [{"service": "EC2", "cost": 100.0, "carbon_kg": 5.0}]
    }

    with (
        patch.object(
            CostAggregator, "get_basic_breakdown", return_value=breakdown_data
        ),
        patch.object(
            CostAggregator, "get_data_freshness", return_value={"status": "final"}
        ),
        patch.object(
            CostAggregator,
            "get_canonical_data_quality",
            return_value={"mapped_percentage": 100.0, "meets_target": True},
        ),
    ):
        res = await CostAggregator.get_dashboard_summary(
            mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )
    assert res["total_cost"] == 100.0


@pytest.mark.asyncio
async def test_get_dashboard_summary_includes_data_quality(mock_db, tenant_id):
    row = MagicMock()
    row.total_cost = Decimal("100.00")
    row.total_carbon = Decimal("5.00")

    mock_result = MagicMock()
    mock_result.one_or_none.return_value = row
    mock_db.execute.return_value = mock_result

    with (
        patch.object(
            CostAggregator, "get_basic_breakdown", return_value={"breakdown": []}
        ),
        patch.object(
            CostAggregator,
            "get_data_freshness",
            return_value={"status": "mixed", "freshness_percentage": 80.0},
        ),
        patch.object(
            CostAggregator,
            "get_canonical_data_quality",
            return_value={"mapped_percentage": 99.2, "meets_target": True},
        ),
    ):
        res = await CostAggregator.get_dashboard_summary(
            mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )

    assert "data_quality" in res
    assert res["data_quality"]["freshness"]["status"] == "mixed"
    assert res["data_quality"]["canonical_mapping"]["mapped_percentage"] == 99.2


@pytest.mark.asyncio
async def test_get_canonical_data_quality_no_data(mock_db, tenant_id):
    mock_row = MagicMock()
    mock_row.total_records = 0
    mock_row.mapped_records = 0

    main_result = MagicMock()
    main_result.one_or_none.return_value = mock_row
    top_result = MagicMock()
    top_result.all.return_value = []
    reason_result = MagicMock()
    reason_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [main_result, top_result, reason_result]

    result = await CostAggregator.get_canonical_data_quality(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )

    assert result["status"] == "no_data"
    assert result["mapped_percentage"] == 0.0
    assert result["meets_target"] is False
    assert result["top_unmapped_signatures"] == []


@pytest.mark.asyncio
async def test_get_canonical_data_quality_below_target(mock_db, tenant_id):
    mock_row = MagicMock()
    mock_row.total_records = 100
    mock_row.mapped_records = 97

    main_result = MagicMock()
    main_result.one_or_none.return_value = mock_row
    top_result = MagicMock()
    top_result.all.return_value = []
    reason_result = MagicMock()
    reason_result.scalars.return_value.all.return_value = []
    mock_db.execute.side_effect = [main_result, top_result, reason_result]

    result = await CostAggregator.get_canonical_data_quality(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )

    assert result["status"] == "warning"
    assert result["mapped_percentage"] == 97.0
    assert result["unmapped_records"] == 3
    assert result["meets_target"] is False


@pytest.mark.asyncio
async def test_get_canonical_data_quality_reason_and_signature_details(
    mock_db, tenant_id
):
    row = MagicMock()
    row.total_records = 10
    row.mapped_records = 8

    main_result = MagicMock()
    main_result.one_or_none.return_value = row

    top_row = MagicMock()
    top_row.provider = None
    top_row.service = None
    top_row.usage_type = None
    top_row.record_count = 2
    top_row.first_seen = date(2026, 1, 1)
    top_row.last_seen = date(2026, 1, 31)
    top_result = MagicMock()
    top_result.all.return_value = [top_row]

    reason_result = MagicMock()
    reason_result.scalars.return_value.all.return_value = [
        "invalid",
        {"canonical_mapping": "invalid"},
        {"canonical_mapping": {"unmapped_reason": " "}},
        {"canonical_mapping": {"unmapped_reason": "missing_rule"}},
    ]

    mock_db.execute.side_effect = [main_result, top_result, reason_result]

    result = await CostAggregator.get_canonical_data_quality(
        mock_db,
        tenant_id,
        date(2026, 1, 1),
        date(2026, 1, 31),
        provider="aws",
    )

    assert result["sampled_unmapped_records"] == 4
    assert result["top_unmapped_signatures"][0]["provider"] == "unknown"
    assert result["top_unmapped_signatures"][0]["service"] == "Unknown"
    assert result["top_unmapped_signatures"][0]["usage_type"] == "Unknown"
    assert result["unmapped_reason_breakdown"]["unknown"] == 1
    assert result["unmapped_reason_breakdown"]["missing_rule"] == 1


@pytest.mark.asyncio
async def test_get_basic_breakdown(mock_db, tenant_id):
    row1 = MagicMock()
    row1.service = "EC2"
    row1.total_cost = Decimal("50.00")
    row1.total_carbon = Decimal("2.0")
    row2 = MagicMock()
    row2.service = None
    row2.total_cost = Decimal("10.00")
    row2.total_carbon = Decimal("0.5")

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2]
    mock_db.execute.return_value = mock_result

    res = await CostAggregator.get_basic_breakdown(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["total_cost"] == 60.0


@pytest.mark.asyncio
async def test_get_governance_report(mock_db, tenant_id):
    row = MagicMock()
    row.total_untagged_cost = Decimal("20.00")
    row.untagged_count = 5
    mock_result = MagicMock()
    mock_result.one.return_value = row

    mock_total_result = MagicMock()
    mock_total_result.scalar.return_value = Decimal("100.00")
    mock_db.execute.side_effect = [mock_total_result, mock_result]

    with patch(
        "app.modules.reporting.domain.attribution_engine.AttributionEngine"
    ) as mock_engine_cls:
        mock_engine = mock_engine_cls.return_value
        mock_engine.get_unallocated_analysis = AsyncMock(return_value=[])
        res = await CostAggregator.get_governance_report(
            mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )
    assert res["unallocated_percentage"] == 20.0


@pytest.mark.asyncio
async def test_get_cached_breakdown_hit(mock_db, tenant_id):
    row = MagicMock()
    row.service = "S3"
    row.total_cost = Decimal("30.00")
    row.total_carbon = Decimal("1.0")
    mock_result = MagicMock()
    mock_result.all.return_value = [row]
    mock_db.execute.return_value = mock_result
    mock_db.begin_nested.return_value.__aenter__.return_value = MagicMock()

    res = await CostAggregator.get_cached_breakdown(
        mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert res["cached"] is True


@pytest.mark.asyncio
async def test_get_cached_breakdown_fallback(mock_db, tenant_id):
    mock_db.begin_nested.side_effect = Exception("MV fail")
    fallback_data = {"total_cost": 10.0, "breakdown": []}
    with patch.object(
        CostAggregator, "get_basic_breakdown", return_value=fallback_data
    ):
        res = await CostAggregator.get_cached_breakdown(
            mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )
    assert res["total_cost"] == 10.0


@pytest.mark.asyncio
async def test_get_cached_breakdown_empty_cache_rows_fallback(mock_db, tenant_id):
    empty_result = MagicMock()
    empty_result.all.return_value = []
    mock_db.execute.return_value = empty_result
    mock_db.begin_nested.return_value.__aenter__.return_value = MagicMock()

    fallback_data = {"total_cost": 22.0, "total_carbon_kg": 1.1, "breakdown": []}
    with patch.object(
        CostAggregator, "get_basic_breakdown", return_value=fallback_data
    ) as fallback:
        res = await CostAggregator.get_cached_breakdown(
            mock_db, tenant_id, date(2026, 1, 1), date(2026, 1, 31)
        )
    fallback.assert_awaited_once()
    assert res["total_cost"] == 22.0


@pytest.mark.asyncio
async def test_refresh_materialized_view_pg(mock_db):
    mock_db.bind.dialect.name = "postgresql"
    res = await CostAggregator.refresh_materialized_view(mock_db)
    assert res is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_materialized_view_sqlite_skip(mock_db):
    mock_db.bind.dialect.name = "sqlite"
    res = await CostAggregator.refresh_materialized_view(mock_db)
    assert res is True
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_materialized_view_failure(mock_db):
    mock_db.bind.dialect.name = "postgresql"
    mock_db.execute.side_effect = Exception("refresh failed")
    res = await CostAggregator.refresh_materialized_view(mock_db)
    assert res is False
