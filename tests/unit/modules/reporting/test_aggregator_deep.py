"""
Tests for CostAggregator module.
Covers aggregation summaries, dashboard data, and governance reports.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, date
from decimal import Decimal
import uuid

from app.modules.reporting.domain.aggregator import CostAggregator
from app.models.cloud import CostRecord

@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    # Mock dialects for specific checks
    session.bind.dialect.name = "postgresql"
    return session

@pytest.fixture
def tenant_id():
    """Create a test tenant ID."""
    return uuid.uuid4()

class TestCostAggregator:
    """Test CostAggregator static methods."""

    @pytest.mark.asyncio
    async def test_count_records(self, mock_db, tenant_id):
        """Test counting records."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_db.execute.return_value = mock_result

        count = await CostAggregator.count_records(
            mock_db, 
            tenant_id, 
            date.today(), 
            date.today()
        )
        
        assert count == 42
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_data_freshness_no_data(self, mock_db, tenant_id):
        """Test freshness check with no data."""
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await CostAggregator.get_data_freshness(
            mock_db, tenant_id, date.today(), date.today()
        )

        assert result["status"] == "no_data"
        assert result["total_records"] == 0

    @pytest.mark.asyncio
    async def test_get_data_freshness_mixed(self, mock_db, tenant_id):
        """Test freshness mixed status."""
        mock_row = MagicMock()
        mock_row.total_records = 100
        mock_row.preliminary_count = 20
        mock_row.final_count = 80
        mock_row.latest_record_date = date.today()
        
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        mock_db.execute.return_value = mock_result

        result = await CostAggregator.get_data_freshness(
            mock_db, tenant_id, date.today(), date.today()
        )

        assert result["status"] == "mixed"
        assert result["freshness_percentage"] == 80.0

    @pytest.mark.asyncio
    async def test_get_summary(self, mock_db, tenant_id):
        """Test fetching cost summary with accurate totals."""
        r1 = MagicMock(spec=CostRecord)
        r1.cost_usd = Decimal("10.50")
        r1.service = "ec2"
        r1.region = "us-east-1"
        r1.recorded_at = datetime.now()
        
        r2 = MagicMock(spec=CostRecord)
        r2.cost_usd = Decimal("5.50")
        r2.service = "rds"
        r2.region = "us-west-1"
        r2.recorded_at = datetime.now()

        # Mock accurate total result
        mock_total_row = MagicMock()
        mock_total_row.total_cost = Decimal("16.00")
        mock_total_row.total_count = 2
        mock_total_res = MagicMock()
        mock_total_res.one.return_value = mock_total_row

        # Mock records result
        mock_records_res = MagicMock()
        mock_records_res.scalars.return_value.all.return_value = [r1, r2]

        mock_db.execute.side_effect = [mock_total_res, mock_records_res]

        summary = await CostAggregator.get_summary(
            mock_db, tenant_id, date.today(), date.today()
        )

        assert summary.total_cost == Decimal("16.00")
        assert summary.by_service["ec2"] == Decimal("10.50")
        assert summary.metadata["is_truncated"] is False
        assert summary.metadata["total_records_in_range"] == 2

    @pytest.mark.asyncio
    async def test_get_summary_truncation(self, mock_db, tenant_id):
        """Test summary truncation logic and accurate totals."""
        from app.modules.reporting.domain.aggregator import MAX_DETAIL_ROWS
        
        # Mock accurate total result (exceeding limit)
        mock_total_row = MagicMock()
        mock_total_row.total_cost = Decimal("5000.00")
        mock_total_row.total_count = MAX_DETAIL_ROWS + 100
        mock_total_res = MagicMock()
        mock_total_res.one.return_value = mock_total_row

        # Mock truncated records result
        mock_records = []
        for i in range(5): # Just return 5 for the test
             r = MagicMock(spec=CostRecord)
             r.cost_usd = Decimal("10.00")
             r.service = "ec2"
             r.region = "us-east-1"
             r.recorded_at = datetime.now()
             mock_records.append(r)
             
        mock_records_res = MagicMock()
        mock_records_res.scalars.return_value.all.return_value = mock_records

        mock_db.execute.side_effect = [mock_total_res, mock_records_res]

        summary = await CostAggregator.get_summary(
            mock_db, tenant_id, date.today(), date.today()
        )

        assert summary.total_cost == Decimal("5000.00") # Accurate total from DB
        assert summary.metadata["is_truncated"] is True
        assert summary.metadata["total_records_in_range"] == MAX_DETAIL_ROWS + 100
        assert summary.metadata["records_returned"] == 5
        assert summary.metadata["summary"] == "Breakdown/records are partial"

    @pytest.mark.asyncio
    async def test_get_dashboard_summary(self, mock_db, tenant_id):
        """Test dashboard summary aggregation."""
        # Mock summary row
        mock_row = MagicMock()
        mock_row.total_cost = Decimal("100.00")
        mock_row.total_carbon = Decimal("50.00")
        
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = mock_row
        
        # Mock breakdown for get_basic_breakdown call
        mock_breakdown_rows = [
            MagicMock(service="ec2", total_cost=Decimal("60.00"), total_carbon=Decimal("30.00")),
            MagicMock(service="s3", total_cost=Decimal("40.00"), total_carbon=Decimal("20.00"))
        ]
        
        # We need to handle multiple execute calls (one for summary, one for breakdown)
        # Using side_effect to return different mocks
        mock_breakdown_result = MagicMock()
        mock_breakdown_result.all.return_value = mock_breakdown_rows
        
        mock_db.execute.side_effect = [
             # First call is setting timeout (if standard DB) or summary query
             # Since fixture sets dialect to postgres, it calls SET LOCAL first?
             # Let's see code.
             # get_dashboard_summary calls execute(SET...), then execute(stmt).
             # get_basic_breakdown calls execute(SET...), then execute(stmt).
             # So 4 calls total.
             MagicMock(), # SET timeout
             mock_result, # Summary query
             MagicMock(), # SET timeout
             mock_breakdown_result # Breakdown query
        ]

        with (
            patch.object(CostAggregator, "get_data_freshness", return_value={"status": "final"}),
            patch.object(
                CostAggregator,
                "get_canonical_data_quality",
                return_value={"mapped_percentage": 100.0, "meets_target": True},
            ),
        ):
            summary = await CostAggregator.get_dashboard_summary(
                mock_db, tenant_id, date.today(), date.today()
            )

        assert summary["total_cost"] == 100.0
        assert summary["total_carbon_kg"] == 50.0
        assert len(summary["breakdown"]) == 2

    @pytest.mark.asyncio
    async def test_get_basic_breakdown(self, mock_db, tenant_id):
        """Test basic cost breakdown."""
        mock_rows = [
            MagicMock(service="ec2", total_cost=Decimal("50.00"), total_carbon=Decimal("10.00")),
            MagicMock(service="lambda", total_cost=Decimal("20.00"), total_carbon=Decimal("5.00"))
        ]
        
        mock_result = MagicMock()
        mock_result.all.return_value = mock_rows
        
        # Handle timeout + query
        mock_db.execute.side_effect = [MagicMock(), mock_result]

        result = await CostAggregator.get_basic_breakdown(
            mock_db, tenant_id, date.today(), date.today()
        )

        assert result["total_cost"] == 70.0
        assert result["total_carbon_kg"] == 15.0
        assert len(result["breakdown"]) == 2
        assert result["breakdown"][0]["service"] == "ec2"

    @pytest.mark.asyncio
    async def test_get_governance_report(self, mock_db, tenant_id):
        """Test governance report generation."""
        # Mock total cost query
        mock_total_res = MagicMock()
        mock_total_res.scalar.return_value = Decimal("1000.00")
        
        # Mock untagged query
        mock_untagged_row = MagicMock()
        mock_untagged_row.total_untagged_cost = Decimal("150.00") # 15%
        mock_untagged_row.untagged_count = 10
        
        mock_untagged_res = MagicMock()
        mock_untagged_res.one.return_value = mock_untagged_row
        
        # Mock AttributionEngine
        # It's imported inside the method, so we must patch the source
        with patch("app.modules.reporting.domain.attribution_engine.AttributionEngine") as MockEngine:
            mock_engine_instance = MockEngine.return_value
            mock_engine_instance.get_unallocated_analysis = AsyncMock(return_value=["Insight 1"])
            
            mock_db.execute.side_effect = [mock_total_res, mock_untagged_res]

            report = await CostAggregator.get_governance_report(
                mock_db, tenant_id, date.today(), date.today()
            )

            assert report["total_cost"] == 1000.0
            assert report["unallocated_cost"] == 150.0
            assert report["unallocated_percentage"] == 15.0
            assert report["status"] == "warning"
            assert report["insights"] == ["Insight 1"]
