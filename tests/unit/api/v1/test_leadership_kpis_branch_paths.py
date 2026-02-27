from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


@pytest.fixture
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


@pytest.fixture
def _quarterly_payload(_leadership_payload):
    from app.modules.reporting.domain.commercial_reports import (
        QuarterlyCommercialProofResponse,
    )
    from app.modules.reporting.domain.savings_proof import (
        SavingsProofBreakdownItem,
        SavingsProofResponse,
    )

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
        leadership_kpis=_leadership_payload,
        savings_proof=savings,
        notes=[],
    )


@pytest.mark.asyncio
async def test_get_leadership_kpis_requires_tenant_context(async_client, app):
    from app.shared.core.auth import CurrentUser, UserRole, get_current_user
    from app.shared.core.pricing import PricingTier

    user = CurrentUser(
        id=uuid4(),
        email="tenantless@valdrix.io",
        tenant_id=None,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = await async_client.get("/api/v1/leadership/kpis")
        assert response.status_code == 403
        assert response.json()["message"] == "Tenant context is required"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_leadership_kpis_maps_service_value_error(async_client, app, test_tenant):
    from app.shared.core.auth import CurrentUser, UserRole, get_current_user
    from app.shared.core.pricing import PricingTier

    user = CurrentUser(
        id=uuid4(),
        email="leadership-errors@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.leadership.LeadershipKpiService.compute",
            new=AsyncMock(side_effect=ValueError("invalid leadership window")),
        ):
            response = await async_client.get(
                "/api/v1/leadership/kpis",
                params={"start_date": "2026-02-10", "end_date": "2026-02-01"},
        )
        assert response.status_code == 400
        assert response.json()["message"] == "invalid leadership window"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_leadership_evidence_skips_invalid_payloads(
    async_client,
    app,
    db,
    test_tenant,
    _leadership_payload,
):
    from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLog
    from app.shared.core.auth import CurrentUser, UserRole, get_current_user
    from app.shared.core.pricing import PricingTier

    user = CurrentUser(
        id=uuid4(),
        email="leadership-admin@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user

    valid_row = AuditLog(
        tenant_id=test_tenant.id,
        event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
        event_timestamp=datetime(2026, 2, 1, 9, 0, 0),
        details={"leadership_kpis": _leadership_payload.model_dump()},
        success=True,
    )
    invalid_type_row = AuditLog(
        tenant_id=test_tenant.id,
        event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
        event_timestamp=datetime(2026, 2, 1, 8, 0, 0),
        details={"leadership_kpis": "not-a-dict"},
        success=True,
    )
    invalid_schema_row = AuditLog(
        tenant_id=test_tenant.id,
        event_type=AuditEventType.LEADERSHIP_KPIS_CAPTURED.value,
        event_timestamp=datetime(2026, 2, 1, 7, 0, 0),
        details={"leadership_kpis": {"start_date": "2026-01-01"}},
        success=True,
    )
    db.add_all([valid_row, invalid_type_row, invalid_schema_row])
    await db.commit()

    try:
        response = await async_client.get("/api/v1/leadership/kpis/evidence", params={"limit": 25})
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["event_id"] == str(valid_row.id)
        assert payload["items"][0]["total_cost_usd"] == 100.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_quarterly_report_maps_service_value_error(
    async_client,
    app,
    test_tenant,
):
    from app.shared.core.auth import CurrentUser, UserRole, get_current_user
    from app.shared.core.pricing import PricingTier

    user = CurrentUser(
        id=uuid4(),
        email="quarterly-errors@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user

    try:
        with patch(
            "app.modules.reporting.api.v1.leadership.CommercialProofReportService.quarterly_report",
            new=AsyncMock(side_effect=ValueError("invalid report request")),
        ):
            response = await async_client.get(
                "/api/v1/leadership/reports/quarterly",
                params={"year": 2026, "quarter": 1},
        )
        assert response.status_code == 400
        assert response.json()["message"] == "invalid report request"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_quarterly_evidence_skips_invalid_payloads(
    async_client,
    app,
    db,
    test_tenant,
    _quarterly_payload,
):
    from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLog
    from app.shared.core.auth import CurrentUser, UserRole, get_current_user
    from app.shared.core.pricing import PricingTier

    user = CurrentUser(
        id=uuid4(),
        email="quarterly-admin@valdrix.io",
        tenant_id=test_tenant.id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user

    valid_row = AuditLog(
        tenant_id=test_tenant.id,
        event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value,
        event_timestamp=datetime(2026, 2, 5, 9, 0, 0),
        details={"quarterly_report": _quarterly_payload.model_dump()},
        success=True,
    )
    invalid_row = AuditLog(
        tenant_id=test_tenant.id,
        event_type=AuditEventType.COMMERCIAL_QUARTERLY_REPORT_CAPTURED.value,
        event_timestamp=datetime(2026, 2, 5, 8, 0, 0),
        details={"quarterly_report": {"year": 2026}},
        success=True,
    )
    db.add_all([valid_row, invalid_row])
    await db.commit()

    try:
        response = await async_client.get(
            "/api/v1/leadership/reports/quarterly/evidence", params={"limit": 25}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        assert payload["items"][0]["event_id"] == str(valid_row.id)
        assert payload["items"][0]["year"] == 2026
    finally:
        app.dependency_overrides.pop(get_current_user, None)
