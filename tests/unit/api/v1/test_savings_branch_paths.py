from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from app.modules.reporting.api.v1 import savings as savings_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id: object | None = None) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="savings@example.com",
        tenant_id=tenant_id if tenant_id is not None else uuid4(),
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _scalars_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


def _all_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = items
    return result


def _proof_payload():
    from app.modules.reporting.domain.savings_proof import (
        SavingsProofBreakdownItem,
        SavingsProofResponse,
    )

    return SavingsProofResponse(
        start_date="2026-02-01",
        end_date="2026-02-28",
        as_of="2026-02-28T23:59:59+00:00",
        tier="pro",
        opportunity_monthly_usd=120.0,
        realized_monthly_usd=55.0,
        open_recommendations=3,
        applied_recommendations=2,
        pending_remediations=1,
        completed_remediations=4,
        breakdown=[
            SavingsProofBreakdownItem(
                provider="aws",
                opportunity_monthly_usd=120.0,
                realized_monthly_usd=55.0,
                open_recommendations=3,
                applied_recommendations=2,
                pending_remediations=1,
                completed_remediations=4,
            )
        ],
        notes=[],
    )


def _drilldown_payload():
    from app.modules.reporting.domain.savings_proof import (
        SavingsProofDrilldownBucket,
        SavingsProofDrilldownResponse,
    )

    return SavingsProofDrilldownResponse(
        start_date="2026-02-01",
        end_date="2026-02-28",
        as_of="2026-02-28T23:59:59+00:00",
        tier="pro",
        provider="aws",
        dimension="strategy_type",
        opportunity_monthly_usd=120.0,
        realized_monthly_usd=55.0,
        buckets=[
            SavingsProofDrilldownBucket(
                key="savings_plan",
                opportunity_monthly_usd=120.0,
                realized_monthly_usd=55.0,
                open_recommendations=3,
                applied_recommendations=2,
                pending_remediations=1,
                completed_remediations=4,
            )
        ],
        truncated=False,
        limit=50,
        notes=[],
    )


def test_require_tenant_id_rejects_missing_tenant() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="savings-no-tenant@example.com",
        tenant_id=None,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    with pytest.raises(HTTPException) as exc:
        savings_api._require_tenant_id(user)
    assert exc.value.status_code == 403
    assert "Tenant context required." in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_savings_proof_json_and_csv_paths() -> None:
    payload = _proof_payload()
    user = _user()

    with patch.object(savings_api, "SavingsProofService") as service_cls:
        service = MagicMock()
        service.generate = AsyncMock(return_value=payload)
        service_cls.return_value = service
        service_cls.render_csv.return_value = "metric,value\nopportunity,120.0\n"

        json_response = await savings_api.get_savings_proof(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            provider=" AWS ",
            response_format="json",
            current_user=user,
            db=MagicMock(),
        )
        csv_response = await savings_api.get_savings_proof(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            provider="aws",
            response_format="csv",
            current_user=user,
            db=MagicMock(),
        )

    assert json_response.opportunity_monthly_usd == 120.0
    assert isinstance(csv_response, Response)
    assert csv_response.media_type == "text/csv"
    assert "opportunity,120.0" in csv_response.body.decode()
    assert service.generate.await_args_list[0].kwargs["provider"] == "aws"


@pytest.mark.asyncio
async def test_get_savings_proof_maps_service_value_error() -> None:
    with patch.object(savings_api, "SavingsProofService") as service_cls:
        service = MagicMock()
        service.generate = AsyncMock(side_effect=ValueError("invalid savings window"))
        service_cls.return_value = service
        with pytest.raises(HTTPException) as exc:
            await savings_api.get_savings_proof(
                start_date=date(2026, 2, 28),
                end_date=date(2026, 2, 1),
                provider=None,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )
    assert exc.value.status_code == 400
    assert "invalid savings window" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_savings_proof_drilldown_json_and_csv_paths() -> None:
    payload = _drilldown_payload()
    user = _user()

    with patch.object(savings_api, "SavingsProofService") as service_cls:
        service = MagicMock()
        service.drilldown = AsyncMock(return_value=payload)
        service_cls.return_value = service
        service_cls.render_drilldown_csv.return_value = "key,value\nsavings_plan,120.0\n"

        json_response = await savings_api.get_savings_proof_drilldown(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            provider=" AWS ",
            dimension="strategy_type",
            limit=50,
            response_format="json",
            current_user=user,
            db=MagicMock(),
        )
        csv_response = await savings_api.get_savings_proof_drilldown(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            provider="aws",
            dimension="strategy_type",
            limit=50,
            response_format="csv",
            current_user=user,
            db=MagicMock(),
        )

    assert json_response.dimension == "strategy_type"
    assert json_response.provider == "aws"
    assert isinstance(csv_response, Response)
    assert "savings_plan,120.0" in csv_response.body.decode()
    assert service.drilldown.await_args_list[0].kwargs["provider"] == "aws"


@pytest.mark.asyncio
async def test_get_savings_proof_drilldown_maps_service_value_error() -> None:
    with patch.object(savings_api, "SavingsProofService") as service_cls:
        service = MagicMock()
        service.drilldown = AsyncMock(side_effect=ValueError("invalid drilldown"))
        service_cls.return_value = service
        with pytest.raises(HTTPException) as exc:
            await savings_api.get_savings_proof_drilldown(
                start_date=date(2026, 2, 28),
                end_date=date(2026, 2, 1),
                provider=None,
                dimension="strategy_type",
                limit=50,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )
    assert exc.value.status_code == 400
    assert "invalid drilldown" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_compute_realized_savings_rejects_invalid_window() -> None:
    with pytest.raises(HTTPException) as exc:
        await savings_api.compute_realized_savings(
            start_date=date(2026, 2, 28),
            end_date=date(2026, 2, 1),
            baseline_days=7,
            measurement_days=7,
            gap_days=1,
            monthly_multiplier_days=30,
            require_final=True,
            current_user=_user(),
            db=MagicMock(),
        )
    assert exc.value.status_code == 400
    assert "start_date must be <= end_date" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_compute_realized_savings_handles_computed_skipped_and_errors() -> None:
    remediations = [SimpleNamespace(id=uuid4()) for _ in range(3)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result(remediations))
    db.commit = AsyncMock()

    with patch.object(savings_api, "RealizedSavingsService") as service_cls:
        service = MagicMock()
        service.compute_for_request = AsyncMock(
            side_effect=[object(), None, RuntimeError("compute failed")]
        )
        service_cls.return_value = service

        response = await savings_api.compute_realized_savings(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
            baseline_days=7,
            measurement_days=7,
            gap_days=1,
            monthly_multiplier_days=30,
            require_final=True,
            current_user=_user(),
            db=db,
        )

    assert response.computed == 1
    assert response.skipped == 1
    assert len(response.errors) == 1
    assert "compute failed" in response.errors[0]["error"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_realized_savings_events_rejects_invalid_window() -> None:
    with pytest.raises(HTTPException) as exc:
        await savings_api.list_realized_savings_events(
            start_date=date(2026, 2, 28),
            end_date=date(2026, 2, 1),
            provider=None,
            response_format="json",
            limit=50,
            current_user=_user(),
            db=MagicMock(),
        )
    assert exc.value.status_code == 400
    assert "start_date must be <= end_date" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_realized_savings_events_json_and_csv_paths() -> None:
    request_id = uuid4()
    event = SimpleNamespace(
        remediation_request_id=request_id,
        provider="aws",
        account_id=uuid4(),
        resource_id="i-abc",
        region="us-east-1",
        method="post_action_delta",
        baseline_start_date=date(2026, 1, 1),
        baseline_end_date=date(2026, 1, 7),
        measurement_start_date=date(2026, 1, 8),
        measurement_end_date=date(2026, 1, 14),
        baseline_avg_daily_cost_usd=Decimal("10.50"),
        measurement_avg_daily_cost_usd=Decimal("8.10"),
        realized_monthly_savings_usd=Decimal("72.00"),
        confidence_score=Decimal("0.91"),
        computed_at=datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc),
    )
    executed_at = datetime(2026, 2, 20, 9, 0, tzinfo=timezone.utc)
    db = MagicMock()
    db.execute = AsyncMock(return_value=_all_result([(event, executed_at)]))

    json_response = await savings_api.list_realized_savings_events(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        provider=" AWS ",
        response_format="json",
        limit=200,
        current_user=_user(),
        db=db,
    )
    csv_response = await savings_api.list_realized_savings_events(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
        provider=None,
        response_format="csv",
        limit=200,
        current_user=_user(),
        db=db,
    )

    assert len(json_response) == 1
    assert json_response[0].provider == "aws"
    assert json_response[0].realized_monthly_savings_usd == 72.0
    assert isinstance(csv_response, Response)
    csv_text = csv_response.body.decode()
    assert "realized_monthly_savings_usd" in csv_text
    assert "72.0" in csv_text
