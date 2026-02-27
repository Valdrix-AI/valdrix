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


@pytest.mark.asyncio
async def test_get_leadership_kpis_direct_csv_branch() -> None:
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
            return_value="header,value\nx,1\n",
        ) as render_mock,
    ):
        response = await leadership_api.get_leadership_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider=" AWS ",
            include_preliminary=True,
            top_services_limit=7,
            response_format="csv",
            current_user=_user(),
            db=db,
        )

    assert response.media_type == "text/csv"
    assert response.body.decode() == "header,value\nx,1\n"
    assert "leadership-kpis-2026-01-01-2026-01-31.csv" in response.headers[
        "Content-Disposition"
    ]
    render_mock.assert_called_once_with(payload)
    assert compute_mock.await_args.kwargs["provider"] == "aws"
    assert compute_mock.await_args.kwargs["include_preliminary"] is True
    assert compute_mock.await_args.kwargs["top_services_limit"] == 7


@pytest.mark.asyncio
async def test_get_leadership_kpis_direct_json_branch_returns_payload() -> None:
    payload = _leadership_payload()

    with patch.object(
        leadership_api.LeadershipKpiService,
        "compute",
        new=AsyncMock(return_value=payload),
    ):
        response = await leadership_api.get_leadership_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider=None,
            include_preliminary=False,
            top_services_limit=10,
            response_format="json",
            current_user=_user(),
            db=MagicMock(),
        )

    assert response is payload


@pytest.mark.asyncio
async def test_get_leadership_kpis_direct_maps_value_error() -> None:
    with patch.object(
        leadership_api.LeadershipKpiService,
        "compute",
        new=AsyncMock(side_effect=ValueError("bad leadership query")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.get_leadership_kpis(
                start_date=date(2026, 1, 31),
                end_date=date(2026, 1, 1),
                provider=None,
                include_preliminary=False,
                top_services_limit=10,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert "bad leadership query" in str(exc.value.detail)


def test_leadership_require_tenant_id_rejects_missing_context() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="leadership@example.com",
        tenant_id=None,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    with pytest.raises(HTTPException) as exc:
        leadership_api._require_tenant_id(user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Tenant context is required"


@pytest.mark.asyncio
async def test_capture_leadership_kpis_direct_maps_value_error() -> None:
    with patch.object(
        leadership_api.LeadershipKpiService,
        "compute",
        new=AsyncMock(side_effect=ValueError("invalid leadership window")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.capture_leadership_kpis(
                start_date=date(2026, 2, 10),
                end_date=date(2026, 2, 1),
                provider=None,
                include_preliminary=False,
                top_services_limit=10,
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert "invalid leadership window" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_capture_leadership_kpis_direct_success_logs_and_commits() -> None:
    payload = _leadership_payload()
    db = MagicMock()
    db.commit = AsyncMock()
    event = SimpleNamespace(
        id=uuid4(),
        event_timestamp=datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc),
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

        response = await leadership_api.capture_leadership_kpis(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="gcp",
            include_preliminary=False,
            top_services_limit=5,
            current_user=_user(),
            db=db,
        )

    assert response.status == "captured"
    assert response.event_id == str(event.id)
    assert response.captured_at == event.event_timestamp.isoformat()
    db.commit.assert_awaited_once()
    audit.log.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_leadership_evidence_direct_skips_non_dict_and_invalid_schema() -> None:
    tenant_id = uuid4()
    user = _user(tenant_id=tenant_id)
    payload = _leadership_payload()

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
        success=False,
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
    db.execute = AsyncMock(return_value=_scalars_result([valid_row, invalid_type_row, invalid_schema_row]))

    with patch.object(leadership_api, "logger") as logger_mock:
        response = await leadership_api.list_leadership_kpi_evidence(
            limit=25,
            current_user=user,
            db=db,
        )

    assert response.total == 1
    assert response.items[0].event_id == str(valid_row.id)
    assert response.items[0].actor_id == str(valid_row.actor_id)
    logger_mock.warning.assert_called_once()


@pytest.mark.asyncio
async def test_get_quarterly_report_direct_csv_branch() -> None:
    report = _quarterly_payload()

    with (
        patch.object(
            leadership_api.CommercialProofReportService,
            "quarterly_report",
            new=AsyncMock(return_value=report),
        ) as quarterly_mock,
        patch.object(
            leadership_api.CommercialProofReportService,
            "render_quarterly_csv",
            return_value="quarter,cost\nQ1,100\n",
        ) as render_mock,
    ):
        response = await leadership_api.get_quarterly_commercial_report(
            period="previous",
            year=None,
            quarter=None,
            as_of=date(2026, 3, 31),
            provider=" AWS ",
            response_format="csv",
            current_user=_user(),
            db=MagicMock(),
        )

    assert response.media_type == "text/csv"
    assert "commercial-quarterly-2026-Q1.csv" in response.headers["Content-Disposition"]
    render_mock.assert_called_once_with(report)
    assert quarterly_mock.await_args.kwargs["provider"] == "aws"


@pytest.mark.asyncio
async def test_get_quarterly_report_direct_json_branch_returns_report() -> None:
    report = _quarterly_payload()

    with patch.object(
        leadership_api.CommercialProofReportService,
        "quarterly_report",
        new=AsyncMock(return_value=report),
    ):
        response = await leadership_api.get_quarterly_commercial_report(
            period="previous",
            year=None,
            quarter=None,
            as_of=None,
            provider=None,
            response_format="json",
            current_user=_user(),
            db=MagicMock(),
        )

    assert response is report


@pytest.mark.asyncio
async def test_get_quarterly_report_direct_maps_value_error() -> None:
    with patch.object(
        leadership_api.CommercialProofReportService,
        "quarterly_report",
        new=AsyncMock(side_effect=ValueError("bad quarterly query")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.get_quarterly_commercial_report(
                period="previous",
                year=2026,
                quarter=1,
                as_of=None,
                provider=None,
                response_format="json",
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert "bad quarterly query" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_capture_quarterly_report_direct_maps_value_error() -> None:
    with patch.object(
        leadership_api.CommercialProofReportService,
        "quarterly_report",
        new=AsyncMock(side_effect=ValueError("invalid quarterly request")),
    ):
        with pytest.raises(HTTPException) as exc:
            await leadership_api.capture_quarterly_commercial_report(
                period="previous",
                year=2026,
                quarter=1,
                as_of=None,
                provider=None,
                current_user=_user(),
                db=MagicMock(),
            )

    assert exc.value.status_code == 400
    assert "invalid quarterly request" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_capture_quarterly_report_direct_success_logs_and_commits() -> None:
    report = _quarterly_payload()
    db = MagicMock()
    db.commit = AsyncMock()
    event = SimpleNamespace(
        id=uuid4(),
        event_timestamp=datetime(2026, 2, 26, 13, 0, tzinfo=timezone.utc),
    )

    with (
        patch.object(
            leadership_api.CommercialProofReportService,
            "quarterly_report",
            new=AsyncMock(return_value=report),
        ),
        patch.object(leadership_api, "AuditLogger") as audit_cls,
    ):
        audit = MagicMock()
        audit.log = AsyncMock(return_value=event)
        audit_cls.return_value = audit

        response = await leadership_api.capture_quarterly_commercial_report(
            period="current",
            year=2026,
            quarter=1,
            as_of=date(2026, 3, 31),
            provider="gcp",
            current_user=_user(),
            db=db,
        )

    assert response.status == "captured"
    assert response.event_id == str(event.id)
    assert response.report.year == 2026
    db.commit.assert_awaited_once()
    audit.log.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_quarterly_evidence_direct_skips_non_dict_and_invalid_schema() -> None:
    tenant_id = uuid4()
    user = _user(tenant_id=tenant_id)
    report = _quarterly_payload()

    valid_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-q1",
        event_timestamp=datetime(2026, 2, 5, 9, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email="ops@example.com",
        success=True,
        details={"quarterly_report": report.model_dump()},
    )
    invalid_type_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-q2",
        event_timestamp=datetime(2026, 2, 5, 8, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email=None,
        success=True,
        details={"quarterly_report": ["bad"]},
    )
    invalid_schema_row = SimpleNamespace(
        id=uuid4(),
        correlation_id="run-q3",
        event_timestamp=datetime(2026, 2, 5, 7, 0, tzinfo=timezone.utc),
        actor_id=None,
        actor_email=None,
        success=True,
        details={"quarterly_report": {"year": 2026}},
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=_scalars_result([valid_row, invalid_type_row, invalid_schema_row]))

    with patch.object(leadership_api, "logger") as logger_mock:
        response = await leadership_api.list_quarterly_commercial_report_evidence(
            limit=25,
            current_user=user,
            db=db,
        )

    assert response.total == 1
    assert response.items[0].event_id == str(valid_row.id)
    assert response.items[0].actor_id is None
    logger_mock.warning.assert_called_once()
