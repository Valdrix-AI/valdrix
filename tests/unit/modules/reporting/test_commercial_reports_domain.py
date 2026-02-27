from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.domain.commercial_reports import (
    CommercialProofReportService,
    QuarterlyCommercialProofResponse,
    _previous_full_quarter,
    _quarter_for_date,
    _quarter_window,
)
from app.modules.reporting.domain.leadership_kpis import (
    LeadershipKpisResponse,
    LeadershipTopService,
)
from app.modules.reporting.domain.savings_proof import (
    SavingsProofBreakdownItem,
    SavingsProofResponse,
)
from app.shared.core.pricing import PricingTier


def _leadership_payload() -> LeadershipKpisResponse:
    return LeadershipKpisResponse(
        start_date="2026-01-01",
        end_date="2026-03-31",
        as_of="2026-03-31T00:00:00+00:00",
        tier="pro",
        provider="aws",
        include_preliminary=False,
        total_cost_usd=100.0,
        cost_by_provider={"aws": 100.0},
        top_services=[LeadershipTopService(service="AmazonEC2", cost_usd=100.0)],
        carbon_total_kgco2e=10.0,
        carbon_coverage_percent=100.0,
        savings_opportunity_monthly_usd=60.0,
        savings_realized_monthly_usd=30.0,
        open_recommendations=4,
        applied_recommendations=2,
        pending_remediations=1,
        completed_remediations=3,
        notes=[],
    )


def _savings_payload() -> SavingsProofResponse:
    return SavingsProofResponse(
        start_date="2026-01-01",
        end_date="2026-03-31",
        as_of="2026-03-31T00:00:00+00:00",
        tier="pro",
        opportunity_monthly_usd=60.0,
        realized_monthly_usd=30.0,
        open_recommendations=4,
        applied_recommendations=2,
        pending_remediations=1,
        completed_remediations=3,
        breakdown=[
            SavingsProofBreakdownItem(
                provider="aws",
                opportunity_monthly_usd=60.0,
                realized_monthly_usd=30.0,
                open_recommendations=4,
                applied_recommendations=2,
                pending_remediations=1,
                completed_remediations=3,
            )
        ],
        notes=[],
    )


def test_quarter_window_and_quarter_for_date_helpers() -> None:
    start, end = _quarter_window(2026, 1)
    assert start == date(2026, 1, 1)
    assert end == date(2026, 3, 31)

    with pytest.raises(ValueError, match="quarter must be 1..4"):
        _quarter_window(2026, 0)

    year, quarter, quarter_start = _quarter_for_date(date(2026, 11, 15))
    assert (year, quarter, quarter_start) == (2026, 4, date(2026, 10, 1))


def test_previous_full_quarter_helper() -> None:
    year, quarter, start, end = _previous_full_quarter(date(2026, 2, 20))
    assert year == 2025
    assert quarter == 4
    assert start == date(2025, 10, 1)
    assert end == date(2025, 12, 31)


@pytest.mark.asyncio
async def test_quarterly_report_validates_period_and_explicit_inputs() -> None:
    service = CommercialProofReportService(MagicMock())

    with pytest.raises(ValueError, match="year and quarter must be provided together"):
        await service.quarterly_report(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            year=2026,
            quarter=None,
        )

    with pytest.raises(ValueError, match="period must be 'current' or 'previous'"):
        await service.quarterly_report(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            period="rolling",
        )


@pytest.mark.asyncio
async def test_quarterly_report_explicit_window_calls_services_with_normalized_provider() -> None:
    db = MagicMock()
    service = CommercialProofReportService(db)
    leadership = _leadership_payload()
    savings = _savings_payload()

    with (
        patch(
            "app.modules.reporting.domain.commercial_reports.LeadershipKpiService.compute",
            new=AsyncMock(return_value=leadership),
        ) as compute,
        patch(
            "app.modules.reporting.domain.commercial_reports.SavingsProofService.generate",
            new=AsyncMock(return_value=savings),
        ) as generate,
    ):
        payload = await service.quarterly_report(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            year=2026,
            quarter=1,
            provider=" AWS ",
        )

    assert payload.period == "explicit"
    assert payload.year == 2026
    assert payload.quarter == 1
    assert payload.start_date == "2026-01-01"
    assert payload.end_date == "2026-03-31"
    assert payload.provider == "aws"

    compute.assert_awaited_once()
    generate.assert_awaited_once()
    compute_call = compute.await_args.kwargs
    generate_call = generate.await_args.kwargs
    assert compute_call["provider"] == "aws"
    assert generate_call["provider"] == "aws"
    assert compute_call["start_date"] == date(2026, 1, 1)
    assert compute_call["end_date"] == date(2026, 3, 31)


@pytest.mark.asyncio
async def test_quarterly_report_current_period_window() -> None:
    db = MagicMock()
    service = CommercialProofReportService(db)

    with (
        patch(
            "app.modules.reporting.domain.commercial_reports.LeadershipKpiService.compute",
            new=AsyncMock(return_value=_leadership_payload()),
        ) as compute,
        patch(
            "app.modules.reporting.domain.commercial_reports.SavingsProofService.generate",
            new=AsyncMock(return_value=_savings_payload()),
        ),
    ):
        payload = await service.quarterly_report(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            period="current",
            as_of=date(2026, 2, 20),
        )

    assert payload.period == "current"
    assert payload.year == 2026
    assert payload.quarter == 1
    assert payload.start_date == "2026-01-01"
    assert payload.end_date == "2026-02-20"

    compute_call = compute.await_args.kwargs
    assert compute_call["start_date"] == date(2026, 1, 1)
    assert compute_call["end_date"] == date(2026, 2, 20)


@pytest.mark.asyncio
async def test_quarterly_report_previous_period_window() -> None:
    db = MagicMock()
    service = CommercialProofReportService(db)

    with (
        patch(
            "app.modules.reporting.domain.commercial_reports.LeadershipKpiService.compute",
            new=AsyncMock(return_value=_leadership_payload()),
        ) as compute,
        patch(
            "app.modules.reporting.domain.commercial_reports.SavingsProofService.generate",
            new=AsyncMock(return_value=_savings_payload()),
        ),
    ):
        payload = await service.quarterly_report(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            period="previous",
            as_of=date(2026, 2, 20),
        )

    assert payload.period == "previous"
    assert payload.year == 2025
    assert payload.quarter == 4
    assert payload.start_date == "2025-10-01"
    assert payload.end_date == "2025-12-31"

    compute_call = compute.await_args.kwargs
    assert compute_call["start_date"] == date(2025, 10, 1)
    assert compute_call["end_date"] == date(2025, 12, 31)


def test_render_quarterly_csv_contains_sections() -> None:
    payload = QuarterlyCommercialProofResponse(
        period="explicit",
        year=2026,
        quarter=1,
        start_date="2026-01-01",
        end_date="2026-03-31",
        as_of="2026-03-31T00:00:00+00:00",
        tier="pro",
        provider="aws",
        leadership_kpis=_leadership_payload(),
        savings_proof=_savings_payload(),
        notes=[],
    )
    csv_text = CommercialProofReportService.render_quarterly_csv(payload)

    assert csv_text.startswith("year,quarter,period,start_date,end_date,total_cost_usd")
    assert "cost_by_provider:provider,cost_usd" in csv_text
    assert (
        "savings_by_provider:provider,opportunity_monthly_usd,realized_monthly_usd"
        in csv_text
    )
    assert "top_services:service,cost_usd" in csv_text
