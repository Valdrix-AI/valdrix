from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.shared.llm.delta_analysis import (
    DeltaAnalysisResult,
    DeltaAnalysisService,
    _build_delta_usage_summary,
    analyze_with_delta,
)


@pytest.mark.asyncio
async def test_compute_delta_zero_previous_cost_produces_zero_change_percent_branch() -> None:
    service = DeltaAnalysisService(cache=MagicMock())
    tenant_id = uuid4()
    current = [
        {
            "Groups": [
                {"Keys": ["EC2", "i-1"], "Metrics": {"UnblendedCost": {"Amount": "5.0"}}}
            ]
        }
    ]
    previous = [
        {
            "Groups": [
                {"Keys": ["EC2", "i-1"], "Metrics": {"UnblendedCost": {"Amount": "0"}}}
            ]
        }
    ]

    result = await service.compute_delta(tenant_id, current, previous, days_to_compare=1)
    assert result.top_increases
    assert result.top_increases[0].change_percent == 0


@pytest.mark.asyncio
async def test_compute_delta_tracks_non_significant_delta_without_incrementing_counter() -> None:
    service = DeltaAnalysisService(cache=MagicMock())
    tenant_id = uuid4()
    current = [
        {
            "Groups": [
                {"Keys": ["EC2", "i-1"], "Metrics": {"UnblendedCost": {"Amount": "10.6"}}}
            ]
        }
    ]
    previous = [
        {
            "Groups": [
                {"Keys": ["EC2", "i-1"], "Metrics": {"UnblendedCost": {"Amount": "10.0"}}}
            ]
        }
    ]

    result = await service.compute_delta(tenant_id, current, previous, days_to_compare=1)
    assert len(result.top_increases) == 1
    assert result.significant_changes_count == 0


@pytest.mark.asyncio
async def test_analyze_with_delta_cache_hit_string_json_and_non_dict_json_branches() -> None:
    tenant_id = uuid4()
    analyzer = AsyncMock()
    cache = AsyncMock()

    # Valid JSON dict string returns parsed dict (lines 384-389)
    cache.get_analysis = AsyncMock(return_value='{"status": "cached-json"}')
    with patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache):
        result = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
    assert result == {"status": "cached-json"}

    # Valid JSON but not dict falls back to raw_analysis branch (line 391)
    cache.get_analysis = AsyncMock(return_value='[1,2,3]')
    with patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache):
        result = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
    assert result == {"raw_analysis": "[1,2,3]"}

    # Truthy non-dict/non-str cached value falls through to raw_analysis branch
    cache.get_analysis = AsyncMock(return_value=123)
    with patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache):
        result = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
    assert result == {"raw_analysis": "123"}

    # Invalid JSON cache string hits parse-exception branch
    cache.get_analysis = AsyncMock(return_value='{"broken"')
    with patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache):
        result = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
    assert result == {"raw_analysis": '{"broken"'}


@pytest.mark.asyncio
async def test_analyze_with_delta_force_refresh_skips_cache_lookup() -> None:
    tenant_id = uuid4()
    cache = AsyncMock()
    analyzer = AsyncMock()
    analyzer.analyze = AsyncMock(return_value={"ok": True})

    delta = MagicMock(spec=DeltaAnalysisResult)
    delta.has_significant_changes = True
    delta.significant_changes_count = 1
    delta.as_llm_prompt_data.return_value = {"payload": True}

    with (
        patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache),
        patch.object(DeltaAnalysisService, "compute_delta", new=AsyncMock(return_value=delta)),
    ):
        result = await analyze_with_delta(
            analyzer,
            tenant_id,
            current_costs=[],
            force_refresh=True,
        )

    assert result == {"ok": True}
    cache.get_analysis.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_with_delta_llm_result_string_json_and_raw_fallback() -> None:
    tenant_id = uuid4()
    cache = AsyncMock()
    cache.get_analysis = AsyncMock(return_value=None)

    delta = MagicMock(spec=DeltaAnalysisResult)
    delta.has_significant_changes = True
    delta.significant_changes_count = 2
    delta.as_llm_prompt_data.return_value = {"optimized": True}
    delta.total_current = 12.5

    analyzer = AsyncMock()

    with (
        patch("app.shared.llm.delta_analysis.get_cache_service", return_value=cache),
        patch.object(DeltaAnalysisService, "compute_delta", new=AsyncMock(return_value=delta)),
    ):
        analyzer.analyze = AsyncMock(return_value='{"summary": "ok"}')
        parsed = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
        assert parsed == {"summary": "ok"}

        analyzer.analyze = AsyncMock(return_value='["x"]')
        raw = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
        assert raw == {"raw_analysis": '["x"]'}

        analyzer.analyze = AsyncMock(return_value='{"broken"')
        raw_invalid = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
        assert raw_invalid == {"raw_analysis": '{"broken"'}

        analyzer.analyze = AsyncMock(return_value=object())
        raw_obj = await analyze_with_delta(analyzer, tenant_id, current_costs=[])
        assert raw_obj["raw_analysis"].startswith("<object object")


def test_build_delta_usage_summary_handles_invalid_total_current_values() -> None:
    tenant_id = uuid4()
    delta = DeltaAnalysisResult(tenant_id=tenant_id, analysis_date=date.today())
    delta.total_current = "not-a-number"  # type: ignore[assignment]

    summary = _build_delta_usage_summary(tenant_id, delta, {"p": 1})
    assert str(summary.total_cost) == "0.0"

    delta.total_current = -5  # type: ignore[assignment]
    summary_negative = _build_delta_usage_summary(tenant_id, delta, {"p": 2})
    assert str(summary_negative.total_cost) == "0.0"
    assert summary_negative.metadata == {"delta_payload": {"p": 2}}
