from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.reporting.api.v1 import leadership as leadership_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id: object | None = None) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="leadership@example.com",
        tenant_id=tenant_id if tenant_id is not None else uuid4(),
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _scalars_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _leadership_payload():
    from app.modules.reporting.domain.leadership_kpis import (
        LeadershipKpisResponse,
        LeadershipTopService,
    )

    return LeadershipKpisResponse(
        start_date="2026-01-01",
        end_date="2026-01-31",
        as_of="2026-01-31T00:00:00+00:00",
        tier="pro",
        provider="aws",
        include_preliminary=False,
        total_cost_usd=100.0,
        cost_by_provider={"aws": 100.0},
        top_services=[LeadershipTopService(service="AmazonEC2", cost_usd=100.0)],
        carbon_total_kgco2e=20.0,
        carbon_coverage_percent=100.0,
        savings_opportunity_monthly_usd=50.0,
        savings_realized_monthly_usd=25.0,
        open_recommendations=2,
        applied_recommendations=1,
        pending_remediations=1,
        completed_remediations=1,
        notes=[],
    )


def _quarterly_payload():
    from app.modules.reporting.domain.commercial_reports import (
        QuarterlyCommercialProofResponse,
    )
    from app.modules.reporting.domain.savings_proof import (
        SavingsProofBreakdownItem,
        SavingsProofResponse,
    )

    leadership_payload = _leadership_payload()
    savings = SavingsProofResponse(
        start_date="2026-01-01",
        end_date="2026-03-31",
        as_of="2026-03-31T00:00:00+00:00",
        tier="pro",
        opportunity_monthly_usd=80.0,
        realized_monthly_usd=40.0,
        open_recommendations=4,
        applied_recommendations=2,
        pending_remediations=1,
        completed_remediations=3,
        breakdown=[
            SavingsProofBreakdownItem(
                provider="aws",
                opportunity_monthly_usd=80.0,
                realized_monthly_usd=40.0,
                open_recommendations=4,
                applied_recommendations=2,
                pending_remediations=1,
                completed_remediations=3,
            )
        ],
        notes=[],
    )
    return QuarterlyCommercialProofResponse(
        period="explicit",
        year=2026,
        quarter=1,
        start_date="2026-01-01",
        end_date="2026-03-31",
        as_of="2026-03-31T00:00:00+00:00",
        tier="pro",
        provider="aws",
        leadership_kpis=leadership_payload,
        savings_proof=savings,
        notes=[],
    )


def test_get_leadership_kpis_requires_tenant_context() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="tenantless@valdrics.io",
        tenant_id=None,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    with pytest.raises(HTTPException) as exc:
        leadership_api._require_tenant_id(user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Tenant context is required"


@pytest.mark.asyncio
async def test_get_leadership_kpis_maps_service_value_error() -> None:
    with patch.object(
        leadership_api.LeadershipKpiService,
        "compute",
        new=AsyncMock(side_effect=ValueError("invalid leadership window")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.get_leadership_kpis(
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 1),
                provider=None,
                include_preliminary=False,
                top_services_limit=10,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )
    assert exc.value.status_code == 400
    assert "invalid leadership window" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_leadership_evidence_skips_invalid_payloads() -> None:
    payload = _leadership_payload()
    tenant_id = uuid4()
    user = _user(tenant_id=tenant_id)
    valid_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-1",
        event_timestamp=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
        actor_id=uuid4(),
        actor_email="admin@example.com",
        success=True,
        details={"leadership_kpis": payload.model_dump()},
    )
    invalid_type_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-2",
        event_timestamp=datetime(2026, 2, 1, 8, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email=None,
        success=True,
        details={"leadership_kpis": "not-a-dict"},
    )
    invalid_schema_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-3",
        event_timestamp=datetime(2026, 2, 1, 7, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email=None,
        success=True,
        details={"leadership_kpis": {"start_date": "2026-01-01"}},
    )
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_scalars_result([valid_row, invalid_type_row, invalid_schema_row])
    )

    with patch.object(leadership_api, "logger") as logger_mock:
        response = await leadership_api.list_leadership_kpi_evidence(
            limit=25,
            current_user=user,
            db=db,
        )

    assert response.total == 1
    assert response.items[0].event_id == str(valid_row.id)
    assert response.items[0].total_cost_usd == 100.0
    logger_mock.warning.assert_called_once()


@pytest.mark.asyncio
async def test_get_quarterly_report_maps_service_value_error() -> None:
    with patch.object(
        leadership_api.CommercialProofReportService,
        "quarterly_report",
        new=AsyncMock(side_effect=ValueError("invalid report request")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.get_quarterly_commercial_report(
                period="explicit",
                year=2026,
                quarter=1,
                as_of=None,
                provider=None,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )
    assert exc.value.status_code == 400
    assert "invalid report request" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_quarterly_evidence_skips_invalid_payloads() -> None:
    payload = _quarterly_payload()
    tenant_id = uuid4()
    user = _user(tenant_id=tenant_id)
    valid_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-1",
        event_timestamp=datetime(2026, 2, 5, 9, 0, tzinfo=timezone.utc),
        actor_id=uuid4(),
        actor_email="admin@example.com",
        success=True,
        details={"quarterly_report": payload.model_dump()},
    )
    invalid_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-2",
        event_timestamp=datetime(2026, 2, 5, 8, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email=None,
        success=True,
        details={"quarterly_report": {"year": 2026}},
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([valid_row, invalid_row]))

    with patch.object(leadership_api, "logger") as logger_mock:
        response = await leadership_api.list_quarterly_commercial_report_evidence(
            limit=25,
            current_user=user,
            db=db,
        )

    assert response.total == 1
    assert response.items[0].event_id == str(valid_row.id)
    assert response.items[0].year == 2026
    logger_mock.warning.assert_called_once()
