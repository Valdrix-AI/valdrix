import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import date
from app.shared.llm.delta_analysis import (
    DeltaAnalysisService,
    CostDelta,
    DeltaAnalysisResult,
    analyze_with_delta,
    SIGNIFICANT_CHANGE_PERCENT,
)


@pytest.fixture
def delta_service():
    return DeltaAnalysisService(cache=MagicMock())


class TestDeltaAnalysisExhaustive:
    """Exhaustive tests for DeltaAnalysisService."""

    def test_cost_delta_spike_drop_thresholds(self):
        """Test spike and drop property thresholds (lines 49-57)."""
        # Spike > 50%
        assert CostDelta("r", "t", 10, 16, 6, 60.0).is_spike is True
        assert CostDelta("r", "t", 10, 14, 4, 40.0).is_spike is False

        # Drop < -30%
        assert CostDelta("r", "t", 10, 6, -4, -40.0).is_drop is True
        assert CostDelta("r", "t", 10, 8, -2, -20.0).is_drop is False

    def test_delta_result_has_significant_changes_variants(self):
        """Test has_significant_changes triggers (lines 83-91)."""
        tenant_id = uuid4()
        today = date.today()

        # 1. New resources trigger
        res1 = DeltaAnalysisResult(tenant_id, today, new_resources=[{"id": "r1"}])
        assert res1.has_significant_changes is True

        # 2. Total percent change trigger
        res2 = DeltaAnalysisResult(
            tenant_id, today, total_change_percent=SIGNIFICANT_CHANGE_PERCENT + 1
        )
        assert res2.has_significant_changes is True

        # 3. No changes
        res3 = DeltaAnalysisResult(tenant_id, today)
        assert res3.has_significant_changes is False

    def test_as_llm_prompt_data_slicing(self):
        """Test that prompt data only includes top 5 (lines 116, 125, 127)."""
        res = DeltaAnalysisResult(uuid4(), date.today())
        # Add 10 increases
        res.top_increases = [CostDelta(f"i{i}", "t", 1, 2, 1, 100) for i in range(10)]
        res.top_decreases = [CostDelta(f"d{i}", "t", 2, 1, -1, -50) for i in range(10)]
        res.new_resources = [{"id": f"n{i}"} for i in range(10)]

        data = res.as_llm_prompt_data()
        assert len(data["top_cost_increases"]) == 5
        assert len(data["top_cost_decreases"]) == 5
        assert len(data["new_resources"]) == 5

    @pytest.mark.asyncio
    async def test_compute_delta_new_resource_threshold(self, delta_service):
        """Test new resource minimum cost threshold (line 210)."""
        # Current costs with a tiny new resource ($0.10) and a significant one ($1.10)
        curr = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "tiny"],
                        "Metrics": {"UnblendedCost": {"Amount": "0.10"}},
                    },
                    {
                        "Keys": ["S1", "big"],
                        "Metrics": {"UnblendedCost": {"Amount": "1.10"}},
                    },
                ]
            }
        ]

        res = await delta_service.compute_delta(
            uuid4(), curr, previous_costs=None, days_to_compare=1
        )

        assert len(res.new_resources) == 1
        assert res.new_resources[0]["resource"] == "big"

    @pytest.mark.asyncio
    async def test_compute_delta_removed_resource(self, delta_service):
        """Test removed resource detection (lines 220-225)."""
        prev = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "gone"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.0"}},
                    }
                ]
            }
        ]
        curr = []

        res = await delta_service.compute_delta(
            uuid4(), curr, previous_costs=prev, days_to_compare=1
        )

        assert len(res.removed_resources) == 1
        assert res.removed_resources[0]["resource"] == "gone"

    @pytest.mark.asyncio
    async def test_compute_delta_insignificant_change(self, delta_service):
        """Test skipping insignificant per-resource changes (line 234)."""
        prev = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.0"}},
                    }
                ]
            }
        ]
        curr = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.25"}},
                    }
                ]
            }
        ]  # $0.25 change

        res = await delta_service.compute_delta(uuid4(), curr, prev, 1)
        assert len(res.top_increases) == 0

    def test_aggregate_empty_input(self, delta_service):
        """Test aggregate_by_resource with empty input (line 293)."""
        assert delta_service._aggregate_by_resource([], 3) == {}
        assert delta_service._aggregate_by_resource(None, 3) == {}

    @pytest.mark.asyncio
    async def test_compute_delta_significant_change(self, delta_service):
        """Test significant per-resource changes (lines 237-252)."""
        prev = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.0"}},
                    }
                ]
            }
        ]
        curr = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "15.0"}},
                    }
                ]
            }
        ]  # $5.00 increase

        res = await delta_service.compute_delta(uuid4(), curr, prev, 1)
        assert len(res.top_increases) == 1
        assert res.top_increases[0].change_amount == 5.0
        assert res.significant_changes_count == 1

    @pytest.mark.asyncio
    async def test_compute_delta_significant_decrease(self, delta_service):
        """Test significant per-resource decreases (lines 237-252)."""
        prev = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "10.0"}},
                    }
                ]
            }
        ]
        curr = [
            {
                "Groups": [
                    {
                        "Keys": ["S1", "r"],
                        "Metrics": {"UnblendedCost": {"Amount": "5.0"}},
                    }
                ]
            }
        ]  # $5.00 decrease

        res = await delta_service.compute_delta(uuid4(), curr, prev, 1)
        assert len(res.top_decreases) == 1
        assert res.top_decreases[0].change_amount == -5.0

    def test_aggregate_malformed_aws_data(self, delta_service):
        """Test aggregation with missing keys or metrics (lines 301-312)."""
        # Missing Metrics or UnblendedCost
        bad_data = [
            {
                "Groups": [
                    {"Keys": ["S1", "r1"]},  # No Metrics
                    {"Keys": ["S1", "r2"], "Metrics": {}},  # Empty Metrics
                    {
                        "Keys": [],
                        "Metrics": {"UnblendedCost": {"Amount": "1.0"}},
                    },  # No Keys
                ]
            }
        ]
        res = delta_service._aggregate_by_resource(bad_data, 1)
        assert "r1" not in res
        assert "r2" in res
        assert res["r2"]["total_cost"] == 0.0

    @pytest.mark.asyncio
    async def test_analyze_with_delta_cache_hit(self):
        """Test analyze_with_delta cache hit path (line 357)."""
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value={"status": "cached"})

        with patch(
            "app.shared.llm.delta_analysis.get_cache_service", return_value=mock_cache
        ):
            result = await analyze_with_delta(MagicMock(), uuid4(), [])
            assert result["status"] == "cached"

    @pytest.mark.asyncio
    async def test_analyze_with_delta_no_changes(self):
        """Test analyze_with_delta when no significant changes found (line 370)."""
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value=None)

        # Mock compute_delta to return no changes
        mock_res = MagicMock(spec=DeltaAnalysisResult)
        mock_res.has_significant_changes = False
        mock_res.days_compared = 3
        mock_res.total_change = 0.0
        mock_res.total_change_percent = 0.0

        with (
            patch(
                "app.shared.llm.delta_analysis.get_cache_service",
                return_value=mock_cache,
            ),
            patch.object(
                DeltaAnalysisService, "compute_delta", AsyncMock(return_value=mock_res)
            ),
        ):
            result = await analyze_with_delta(MagicMock(), uuid4(), [])

            assert result["status"] == "no_significant_changes"
            mock_cache.set_analysis.assert_called()

    @pytest.mark.asyncio
    async def test_analyze_with_delta_full_llm_path(self):
        """Test analyze_with_delta reaching the LLM call (line 400)."""
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value=None)
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value={"summary": "llm result"})

        # Mock compute_delta to return significant changes
        mock_res = MagicMock(spec=DeltaAnalysisResult)
        mock_res.has_significant_changes = True
        mock_res.significant_changes_count = 5
        mock_res.as_llm_prompt_data.return_value = {"optimized": "data"}

        with (
            patch(
                "app.shared.llm.delta_analysis.get_cache_service",
                return_value=mock_cache,
            ),
            patch.object(
                DeltaAnalysisService, "compute_delta", AsyncMock(return_value=mock_res)
            ),
        ):
            result = await analyze_with_delta(mock_analyzer, uuid4(), [])
            assert result["summary"] == "llm result"
            mock_analyzer.analyze.assert_called()
