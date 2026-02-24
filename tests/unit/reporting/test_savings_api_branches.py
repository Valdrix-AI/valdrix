from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.modules.reporting.api.v1.savings import (
    _require_tenant_id,
    compute_realized_savings,
    get_savings_proof,
    get_savings_proof_drilldown,
    list_realized_savings_events,
)
from app.modules.reporting.domain.savings_proof import (
    SavingsProofBreakdownItem,
    SavingsProofDrilldownBucket,
    SavingsProofDrilldownResponse,
    SavingsProofResponse,
)
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id=None, role: UserRole = UserRole.ADMIN) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="user@example.com",
        tenant_id=tenant_id,
        role=role,
        tier=PricingTier.PRO,
    )


def _summary_payload() -> SavingsProofResponse:
    return SavingsProofResponse(
        start_date="2026-02-01",
        end_date="2026-02-28",
        as_of="2026-03-01T00:00:00+00:00",
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


def _drilldown_payload() -> SavingsProofDrilldownResponse:
    return SavingsProofDrilldownResponse(
        start_date="2026-02-01",
        end_date="2026-02-28",
        as_of="2026-03-01T00:00:00+00:00",
        tier="pro",
        provider="aws",
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
        notes=["ok"],
    )


def test_require_tenant_id_guard() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_tenant_id(_user(tenant_id=None))
    assert exc.value.status_code == 403
    assert _require_tenant_id(_user(tenant_id=uuid4())) is not None


@pytest.mark.asyncio
async def test_get_savings_proof_value_error_and_csv_response() -> None:
    current_user = _user(tenant_id=uuid4())
    db = AsyncMock()
    start = date(2026, 2, 1)
    end = date(2026, 2, 28)

    with patch(
        "app.modules.reporting.api.v1.savings.SavingsProofService.generate",
        new=AsyncMock(side_effect=ValueError("bad window")),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_savings_proof(
                start_date=start,
                end_date=end,
                provider=None,
                response_format="json",
                current_user=current_user,
                db=db,
            )
    assert exc.value.status_code == 400

    with (
        patch(
            "app.modules.reporting.api.v1.savings.SavingsProofService.generate",
            new=AsyncMock(return_value=_summary_payload()),
        ),
        patch(
            "app.modules.reporting.api.v1.savings.SavingsProofService.render_csv",
            return_value="provider,opportunity_monthly_usd\n",
        ),
    ):
        response = await get_savings_proof(
            start_date=start,
            end_date=end,
            provider=" AWS ",
            response_format="csv",
            current_user=current_user,
            db=db,
        )

    assert isinstance(response, Response)
    assert response.media_type == "text/csv"
    assert "attachment; filename=" in response.headers.get("Content-Disposition", "")


@pytest.mark.asyncio
async def test_get_savings_proof_drilldown_value_error_and_csv_response() -> None:
    current_user = _user(tenant_id=uuid4())
    db = AsyncMock()
    start = date(2026, 2, 1)
    end = date(2026, 2, 28)

    with patch(
        "app.modules.reporting.api.v1.savings.SavingsProofService.drilldown",
        new=AsyncMock(side_effect=ValueError("bad dimension")),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_savings_proof_drilldown(
                start_date=start,
                end_date=end,
                provider=None,
                dimension="strategy_type",
                limit=10,
                response_format="json",
                current_user=current_user,
                db=db,
            )
    assert exc.value.status_code == 400

    with (
        patch(
            "app.modules.reporting.api.v1.savings.SavingsProofService.drilldown",
            new=AsyncMock(return_value=_drilldown_payload()),
        ),
        patch(
            "app.modules.reporting.api.v1.savings.SavingsProofService.render_drilldown_csv",
            return_value="dimension,opportunity_monthly_usd\n",
        ),
    ):
        response = await get_savings_proof_drilldown(
            start_date=start,
            end_date=end,
            provider="AWS",
            dimension="strategy_type",
            limit=10,
            response_format="csv",
            current_user=current_user,
            db=db,
        )

    assert isinstance(response, Response)
    assert response.media_type == "text/csv"
    assert "savings-proof-drilldown-strategy_type" in response.headers.get(
        "Content-Disposition", ""
    )


@pytest.mark.asyncio
async def test_compute_realized_savings_validation_and_partial_results() -> None:
    tenant_id = uuid4()
    current_user = _user(tenant_id=tenant_id, role=UserRole.ADMIN)
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await compute_realized_savings(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 2, 1),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 400

    remediation_ok = SimpleNamespace(id=uuid4())
    remediation_skip = SimpleNamespace(id=uuid4())
    remediation_err = SimpleNamespace(id=uuid4())

    result = MagicMock()
    result.scalars.return_value.all.return_value = [
        remediation_ok,
        remediation_skip,
        remediation_err,
    ]
    db.execute.return_value = result

    with patch(
        "app.modules.reporting.api.v1.savings.RealizedSavingsService.compute_for_request",
        new=AsyncMock(side_effect=[object(), None, RuntimeError("boom")]),
    ):
        payload = await compute_realized_savings(
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
            baseline_days=7,
            measurement_days=7,
            gap_days=1,
            monthly_multiplier_days=30,
            require_final=True,
            current_user=current_user,
            db=db,
        )

    assert payload.computed == 1
    assert payload.skipped == 1
    assert len(payload.errors) == 1
    assert payload.errors[0]["request_id"] == str(remediation_err.id)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_realized_savings_events_json_and_csv_paths() -> None:
    tenant_id = uuid4()
    current_user = _user(tenant_id=tenant_id)
    db = MagicMock()
    db.execute = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await list_realized_savings_events(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 2, 1),
            current_user=current_user,
            db=db,
        )
    assert exc.value.status_code == 400

    event_one = SimpleNamespace(
        remediation_request_id=uuid4(),
        provider="aws",
        account_id=uuid4(),
        resource_id="i-123",
        region="us-east-1",
        method="ledger_delta_avg_daily_v1",
        baseline_start_date=date(2026, 1, 1),
        baseline_end_date=date(2026, 1, 7),
        measurement_start_date=date(2026, 1, 9),
        measurement_end_date=date(2026, 1, 15),
        baseline_avg_daily_cost_usd=10.0,
        measurement_avg_daily_cost_usd=5.0,
        realized_monthly_savings_usd=150.0,
        confidence_score=0.9,
        computed_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    event_two = SimpleNamespace(
        remediation_request_id=uuid4(),
        provider="aws",
        account_id=None,
        resource_id=None,
        region=None,
        method="ledger_delta_avg_daily_v1",
        baseline_start_date=date(2026, 1, 1),
        baseline_end_date=date(2026, 1, 7),
        measurement_start_date=date(2026, 1, 9),
        measurement_end_date=date(2026, 1, 15),
        baseline_avg_daily_cost_usd=None,
        measurement_avg_daily_cost_usd=None,
        realized_monthly_savings_usd=None,
        confidence_score=None,
        computed_at=datetime(2026, 2, 2, tzinfo=timezone.utc),
    )
    execute_result = MagicMock()
    execute_result.all.return_value = [
        (event_one, datetime(2026, 2, 1, tzinfo=timezone.utc)),
        (event_two, "not-a-datetime"),
    ]
    db.execute.return_value = execute_result

    events = await list_realized_savings_events(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        provider="aws",
        response_format="json",
        limit=200,
        current_user=current_user,
        db=db,
    )
    assert len(events) == 2
    assert events[0].provider == "aws"
    assert events[1].executed_at is None

    response = await list_realized_savings_events(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        provider=None,
        response_format="csv",
        limit=200,
        current_user=current_user,
        db=db,
    )
    assert isinstance(response, Response)
    assert response.media_type == "text/csv"
    assert "realized_monthly_savings_usd" in response.body.decode()
