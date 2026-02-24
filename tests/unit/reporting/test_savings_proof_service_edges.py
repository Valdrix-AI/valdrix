from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.domain.savings_proof import (
    SavingsProofBreakdownItem,
    SavingsProofDrilldownBucket,
    SavingsProofDrilldownResponse,
    SavingsProofResponse,
    SavingsProofService,
)


def _result(rows):
    result = MagicMock()
    result.all.return_value = rows
    return result


def _scalar_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_generate_and_drilldown_validate_inputs() -> None:
    service = SavingsProofService(MagicMock())
    tenant_id = uuid4()
    with pytest.raises(ValueError):
        await service.generate(
            tenant_id=tenant_id,
            tier="pro",
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 1),
        )
    with pytest.raises(ValueError):
        await service.drilldown(
            tenant_id=tenant_id,
            tier="pro",
            start_date=date(2026, 2, 10),
            end_date=date(2026, 2, 1),
            dimension="provider",
        )
    with pytest.raises(ValueError):
        await service.drilldown(
            tenant_id=tenant_id,
            tier="pro",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
            dimension="bad_dimension",
        )


@pytest.mark.asyncio
async def test_provider_drilldown_reuses_generate_and_clamps_limit() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    service = SavingsProofService(db)

    summary = SavingsProofResponse(
        start_date="2026-02-01",
        end_date="2026-02-02",
        as_of="2026-02-03T00:00:00+00:00",
        tier="pro",
        opportunity_monthly_usd=12.0,
        realized_monthly_usd=8.0,
        open_recommendations=1,
        applied_recommendations=1,
        pending_remediations=1,
        completed_remediations=1,
        breakdown=[
            SavingsProofBreakdownItem(
                provider="aws",
                opportunity_monthly_usd=12.0,
                realized_monthly_usd=8.0,
                open_recommendations=1,
                applied_recommendations=1,
                pending_remediations=1,
                completed_remediations=1,
            )
        ],
        notes=["ok"],
    )
    with patch.object(service, "generate", new=AsyncMock(return_value=summary)) as gen:
        response = await service.drilldown(
            tenant_id=tenant_id,
            tier="pro",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
            dimension="provider",
            limit=999,
        )

    gen.assert_awaited_once()
    assert response.dimension == "provider"
    assert response.limit == 200
    assert response.truncated is False
    assert response.buckets[0].key == "aws"


@pytest.mark.asyncio
async def test_strategy_type_drilldown_truncates_to_limit() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(
                [
                    ("reserved_instance", Decimal("10"), 1),
                    ("compute_sp", Decimal("9"), 1),
                ]
            ),
            _result(
                [
                    ("reserved_instance", Decimal("3"), 1),
                    ("compute_sp", Decimal("2"), 1),
                ]
            ),
        ]
    )
    service = SavingsProofService(db)

    response = await service.drilldown(
        tenant_id=tenant_id,
        tier="pro",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        dimension="strategy_type",
        limit=1,
    )

    assert response.dimension == "strategy_type"
    assert response.truncated is True
    assert len(response.buckets) == 1
    assert any("truncated to top 1" in note for note in response.notes)


@pytest.mark.asyncio
async def test_remediation_action_drilldown_uses_evidence_and_fallback_rows() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result([("stop_instance", Decimal("7"), 2)]),  # pending
            _result([("stop_instance", 1), ("terminate_instance", 1)]),  # completed
            _result([("stop_instance", Decimal("4"))]),  # evidence
            _result([("terminate_instance", Decimal("3"))]),  # fallback estimate
        ]
    )
    service = SavingsProofService(db)

    response = await service.drilldown(
        tenant_id=tenant_id,
        tier="pro",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        dimension="remediation_action",
    )

    assert response.dimension == "remediation_action"
    by_key = {item.key: item for item in response.buckets}
    assert by_key["stop_instance"].pending_remediations == 2
    assert by_key["stop_instance"].realized_monthly_usd == 4.0
    assert by_key["terminate_instance"].realized_monthly_usd == 3.0
    assert response.realized_monthly_usd == 7.0


@pytest.mark.asyncio
async def test_generate_provider_filter_and_realized_event_override() -> None:
    tenant_id = uuid4()
    in_window = datetime(2026, 2, 15, tzinfo=timezone.utc)
    out_window = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request_id = uuid4()

    open_rows = [
        (SimpleNamespace(estimated_monthly_savings=Decimal("10")), "aws"),
        (SimpleNamespace(estimated_monthly_savings=Decimal("7")), "gcp"),
    ]
    pending_rows = [
        SimpleNamespace(provider="aws", estimated_monthly_savings=Decimal("2")),
        SimpleNamespace(provider="gcp", estimated_monthly_savings=Decimal("4")),
    ]
    applied_rows = [
        (SimpleNamespace(estimated_monthly_savings=Decimal("5")), "aws"),
        (SimpleNamespace(estimated_monthly_savings=Decimal("9")), "gcp"),
    ]
    completed_rows = [
        SimpleNamespace(
            id=request_id,
            provider="aws",
            estimated_monthly_savings=Decimal("3"),
            executed_at=in_window,
            updated_at=None,
            created_at=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            provider="aws",
            estimated_monthly_savings=Decimal("8"),
            executed_at=None,
            updated_at=None,
            created_at=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            provider="aws",
            estimated_monthly_savings=Decimal("8"),
            executed_at=out_window,
            updated_at=None,
            created_at=None,
        ),
    ]
    event_rows = [
        SimpleNamespace(
            remediation_request_id=request_id,
            realized_monthly_savings_usd=Decimal("20"),
        )
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result(open_rows),
            _scalar_result(pending_rows),
            _result(applied_rows),
            _scalar_result(completed_rows),
            _scalar_result(event_rows),
        ]
    )
    service = SavingsProofService(db)

    payload = await service.generate(
        tenant_id=tenant_id,
        tier="pro",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        provider="aws",
    )

    assert payload.open_recommendations == 1
    assert payload.applied_recommendations == 1
    assert payload.pending_remediations == 1
    assert payload.completed_remediations == 1
    assert payload.opportunity_monthly_usd == 12.0
    assert payload.realized_monthly_usd == 25.0
    assert len(payload.breakdown) == 1
    assert payload.breakdown[0].provider == "aws"


@pytest.mark.asyncio
async def test_generate_without_completed_in_window_skips_event_lookup() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            _result([]),
            _scalar_result([]),
            _result([]),
            _scalar_result(
                [
                    SimpleNamespace(
                        id=uuid4(),
                        provider="aws",
                        estimated_monthly_savings=Decimal("3"),
                        executed_at=None,
                        updated_at=None,
                        created_at=None,
                    )
                ]
            ),
        ]
    )
    service = SavingsProofService(db)

    payload = await service.generate(
        tenant_id=tenant_id,
        tier="pro",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    assert payload.opportunity_monthly_usd == 0.0
    assert payload.realized_monthly_usd == 0.0
    assert payload.completed_remediations == 0
    assert db.execute.await_count == 4


def test_render_csv_helpers() -> None:
    summary = SavingsProofResponse(
        start_date="2026-02-01",
        end_date="2026-02-02",
        as_of="2026-02-03T00:00:00+00:00",
        tier="pro",
        opportunity_monthly_usd=12.0,
        realized_monthly_usd=8.0,
        open_recommendations=1,
        applied_recommendations=1,
        pending_remediations=1,
        completed_remediations=1,
        breakdown=[
            SavingsProofBreakdownItem(
                provider="aws",
                opportunity_monthly_usd=12.0,
                realized_monthly_usd=8.0,
                open_recommendations=1,
                applied_recommendations=1,
                pending_remediations=1,
                completed_remediations=1,
            )
        ],
        notes=[],
    )
    csv_text = SavingsProofService.render_csv(summary)
    assert csv_text.startswith("provider,opportunity_monthly_usd")
    assert "TOTAL,12.00,8.00,1,1,1,1" in csv_text

    drilldown = SavingsProofDrilldownResponse(
        start_date="2026-02-01",
        end_date="2026-02-02",
        as_of="2026-02-03T00:00:00+00:00",
        tier="pro",
        provider=None,
        dimension="strategy_type",
        opportunity_monthly_usd=12.0,
        realized_monthly_usd=8.0,
        buckets=[
            SavingsProofDrilldownBucket(
                key="reserved_instance",
                opportunity_monthly_usd=12.0,
                realized_monthly_usd=8.0,
                open_recommendations=1,
                applied_recommendations=1,
                pending_remediations=0,
                completed_remediations=0,
            )
        ],
        truncated=False,
        limit=50,
        notes=[],
    )
    drilldown_csv = SavingsProofService.render_drilldown_csv(drilldown)
    assert drilldown_csv.startswith("strategy_type,opportunity_monthly_usd")
    assert "TOTAL,12.00,8.00,1,1,0,0" in drilldown_csv
