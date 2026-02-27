from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.api.v1 import leadership as leadership_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="leadership@valdrix.io",
        tenant_id=uuid4(),
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _leadership_payload():
    from app.modules.reporting.domain.leadership_kpis import (
        LeadershipKpisResponse,
        LeadershipTopService,
    )

    return LeadershipKpisResponse(
        start_date="2026-02-01",
        end_date="2026-02-01",
        as_of="2026-02-01T23:59:59+00:00",
        tier="pro",
        provider="aws",
        include_preliminary=False,
        total_cost_usd=100.0,
        cost_by_provider={"aws": 100.0},
        top_services=[LeadershipTopService(service="AmazonEC2", cost_usd=100.0)],
        carbon_total_kgco2e=10.0,
        carbon_coverage_percent=100.0,
        savings_opportunity_monthly_usd=12.0,
        savings_realized_monthly_usd=5.0,
        open_recommendations=1,
        applied_recommendations=1,
        pending_remediations=0,
        completed_remediations=1,
        notes=[],
    )


def _scalars_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_get_leadership_kpis_json_and_csv_filters_preliminary() -> None:
    payload = _leadership_payload()
    db = MagicMock()

    with (
        patch.object(
            leadership_api.LeadershipKpiService,
            "compute",
            new=AsyncMock(return_value=payload),
        ) as compute_mock,
        patch.object(
            leadership_api.LeadershipKpiService,
            "render_csv",
            return_value="metric,value\ntotal_cost_usd,100.0000\n",
        ) as render_csv_mock,
    ):
        json_out = await leadership_api.get_leadership_kpis(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            provider=" AWS ",
            include_preliminary=False,
            top_services_limit=10,
            response_format="json",
            current_user=_user(),
            db=db,
        )
        csv_out = await leadership_api.get_leadership_kpis(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            provider="aws",
            include_preliminary=False,
            top_services_limit=10,
            response_format="csv",
            current_user=_user(),
            db=db,
        )

    assert json_out.total_cost_usd == 100.0
    assert json_out.cost_by_provider["aws"] == 100.0
    assert csv_out.media_type == "text/csv"
    assert "total_cost_usd,100.0000" in csv_out.body.decode()
    assert compute_mock.await_count == 2
    assert compute_mock.await_args_list[0].kwargs["provider"] == "aws"
    render_csv_mock.assert_called_once_with(payload)


@pytest.mark.asyncio
async def test_capture_and_list_leadership_kpis_evidence() -> None:
    payload = _leadership_payload()
    user = _user()
    db = MagicMock()
    db.commit = AsyncMock()

    event = SimpleNamespace(
        id=uuid4(),
        event_timestamp=datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc),
        correlation_id="run-1",
        actor_id=user.id,
        actor_email=user.email,
        success=True,
        details={"leadership_kpis": payload.model_dump()},
    )

    with (
        patch.object(
            leadership_api.LeadershipKpiService,
            "compute",
            new=AsyncMock(return_value=payload),
        ),
        patch.object(leadership_api, "AuditLogger") as audit_cls,
    ):
        audit = MagicMock()
        audit.log = AsyncMock(return_value=event)
        audit_cls.return_value = audit

        captured = await leadership_api.capture_leadership_kpis(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 3),
            provider=None,
            include_preliminary=False,
            top_services_limit=10,
            current_user=user,
            db=db,
        )

    assert captured.status == "captured"
    assert captured.leadership_kpis.total_cost_usd == 100.0
    db.commit.assert_awaited_once()

    db.execute = AsyncMock(return_value=_scalars_result([event]))
    listed = await leadership_api.list_leadership_kpi_evidence(
        limit=10,
        current_user=user,
        db=db,
    )
    assert listed.total == 1
    assert listed.items[0].event_id == str(event.id)
    assert listed.items[0].total_cost_usd == 100.0
