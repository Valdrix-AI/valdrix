from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.domain.leadership_kpis import (
    LeadershipKpiService,
    LeadershipKpisResponse,
)
from app.shared.core.pricing import PricingTier


class _Result:
    def __init__(self, *, first_value=None, all_values=None) -> None:
        self._first_value = first_value
        self._all_values = all_values or []

    def first(self):
        return self._first_value

    def all(self):
        return self._all_values


@pytest.mark.asyncio
async def test_compute_rejects_invalid_date_window() -> None:
    db = AsyncMock()
    service = LeadershipKpiService(db)

    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        await service.compute(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 1),
        )


@pytest.mark.asyncio
async def test_compute_rejects_unsupported_provider() -> None:
    db = AsyncMock()
    service = LeadershipKpiService(db)

    with pytest.raises(ValueError, match="Unsupported provider"):
        await service.compute(
            tenant_id=uuid4(),
            tier=PricingTier.PRO,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
            provider="oracle",
        )


@pytest.mark.asyncio
async def test_compute_handles_no_carbon_and_savings_feature_disabled() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _Result(first_value=(Decimal("120.50"), 3, 0, None)),
            _Result(all_values=[("aws", Decimal("120.50"))]),
            _Result(all_values=[("AmazonEC2", Decimal("120.50"))]),
            _Result(first_value=(2, 1, 0)),
        ]
    )

    with patch(
        "app.modules.reporting.domain.leadership_kpis.is_feature_enabled",
        return_value=False,
    ):
        payload = await LeadershipKpiService(db).compute(
            tenant_id=tenant_id,
            tier=PricingTier.STARTER,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            provider=" AWS ",
            include_preliminary=False,
            top_services_limit=10,
        )

    assert payload.provider == "aws"
    assert payload.total_cost_usd == 120.5
    assert payload.carbon_total_kgco2e == 0.0
    assert payload.carbon_coverage_percent == 0.0
    assert payload.cost_by_provider == {"aws": 120.5}
    assert payload.top_services[0].service == "AmazonEC2"
    assert payload.security_high_risk_decisions == 2
    assert payload.security_approval_required_decisions == 1
    assert payload.security_anomaly_signal_decisions == 0
    assert any("Carbon coverage is 0%" in note for note in payload.notes)
    assert any("Savings proof is not enabled" in note for note in payload.notes)


@pytest.mark.asyncio
async def test_compute_includes_savings_when_feature_enabled() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _Result(first_value=(Decimal("200.00"), 2, 2, Decimal("12.34"))),
            _Result(all_values=[("aws", Decimal("150.00")), ("gcp", Decimal("50.00"))]),
            _Result(all_values=[("AmazonEC2", Decimal("120.00")), ("AmazonS3", Decimal("30.00"))]),
            _Result(first_value=(1, 2, 1)),
        ]
    )

    proof = SimpleNamespace(
        opportunity_monthly_usd=88.88,
        realized_monthly_usd=44.44,
        open_recommendations=9,
        applied_recommendations=5,
        pending_remediations=3,
        completed_remediations=7,
    )

    with (
        patch(
            "app.modules.reporting.domain.leadership_kpis.is_feature_enabled",
            return_value=True,
        ),
        patch(
            "app.modules.reporting.domain.leadership_kpis.SavingsProofService"
        ) as proof_service_cls,
    ):
        proof_service_cls.return_value.generate = AsyncMock(return_value=proof)
        payload = await LeadershipKpiService(db).compute(
            tenant_id=tenant_id,
            tier=PricingTier.PRO,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 5),
            provider=None,
            include_preliminary=True,
            top_services_limit=100,
        )

    assert payload.total_cost_usd == 200.0
    assert payload.carbon_total_kgco2e == 12.34
    assert payload.carbon_coverage_percent == 100.0
    assert payload.savings_opportunity_monthly_usd == 88.88
    assert payload.savings_realized_monthly_usd == 44.44
    assert payload.open_recommendations == 9
    assert payload.applied_recommendations == 5
    assert payload.pending_remediations == 3
    assert payload.completed_remediations == 7
    assert payload.security_high_risk_decisions == 1
    assert payload.security_approval_required_decisions == 2
    assert payload.security_anomaly_signal_decisions == 1
    assert payload.notes == []


@pytest.mark.asyncio
async def test_compute_adds_note_when_savings_service_raises() -> None:
    tenant_id = uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _Result(first_value=(Decimal("10.0"), 1, 1, Decimal("1.2"))),
            _Result(all_values=[("aws", Decimal("10.0"))]),
            _Result(all_values=[("AmazonS3", Decimal("10.0"))]),
            _Result(first_value=(0, 0, 0)),
        ]
    )

    with (
        patch(
            "app.modules.reporting.domain.leadership_kpis.is_feature_enabled",
            return_value=True,
        ),
        patch(
            "app.modules.reporting.domain.leadership_kpis.SavingsProofService"
        ) as proof_service_cls,
    ):
        proof_service_cls.return_value.generate = AsyncMock(
            side_effect=RuntimeError("proof unavailable")
        )
        payload = await LeadershipKpiService(db).compute(
            tenant_id=tenant_id,
            tier=PricingTier.PRO,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
        )

    assert any("Savings proof unavailable: proof unavailable" in note for note in payload.notes)
    assert payload.savings_opportunity_monthly_usd == 0.0
    assert payload.savings_realized_monthly_usd == 0.0
    assert payload.security_high_risk_decisions == 0
    assert payload.security_approval_required_decisions == 0
    assert payload.security_anomaly_signal_decisions == 0


def test_render_csv_sorts_provider_rows_by_cost_descending() -> None:
    payload = LeadershipKpisResponse(
        start_date="2026-02-01",
        end_date="2026-02-28",
        as_of="2026-02-28T00:00:00+00:00",
        tier="pro",
        provider=None,
        include_preliminary=False,
        total_cost_usd=100.0,
        cost_by_provider={"gcp": 20.0, "aws": 80.0},
        top_services=[],
        carbon_total_kgco2e=12.0,
        carbon_coverage_percent=100.0,
        savings_opportunity_monthly_usd=25.0,
        savings_realized_monthly_usd=12.0,
        open_recommendations=3,
        applied_recommendations=2,
        pending_remediations=1,
        completed_remediations=1,
        security_high_risk_decisions=2,
        security_approval_required_decisions=3,
        security_anomaly_signal_decisions=1,
        notes=[],
    )

    csv_text = LeadershipKpiService.render_csv(payload)
    lines = csv_text.strip().splitlines()

    assert lines[0].startswith("start_date,end_date,total_cost_usd")
    # provider block header + first provider row should be aws (80) before gcp (20)
    provider_header_index = lines.index("provider,cost_usd")
    assert lines[provider_header_index + 1] == "aws,80.0000"
    assert lines[provider_header_index + 2] == "gcp,20.0000"
