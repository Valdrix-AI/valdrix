from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import URL

from app.modules.reporting.api.v1.costs_models import (
    ProviderInvoiceUpsertRequest,
)
from app.modules.reporting.api.v1.costs_reconciliation_routes import (
    export_focus_v13_costs_csv_impl,
    get_reconciliation_close_package_impl,
    get_restatement_history_impl,
    upsert_provider_invoice_impl,
)
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


class _FakeDB:
    async def commit(self) -> None:
        return None


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        tenant_id=uuid4(),
        email="ops@valdrics.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/costs/reconciliation/invoices",
        "headers": [],
    }
    request = Request(scope)
    request._url = URL("https://api.valdrics.io/api/v1/costs/reconciliation/invoices")
    return request


@pytest.mark.asyncio
async def test_get_reconciliation_close_package_impl_csv_response() -> None:
    user = _user()
    db = _FakeDB()
    with patch(
        "app.modules.reporting.api.v1.costs_reconciliation_routes.CostReconciliationService.generate_close_package",
        new=AsyncMock(return_value={"csv": "a,b\n1,2\n"}),
    ):
        response = await get_reconciliation_close_package_impl(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            response_format="csv",
            enforce_finalized=True,
            user=user,
            db=db,  # type: ignore[arg-type]
            require_tenant_id=lambda u: u.tenant_id,  # type: ignore[return-value]
            normalize_provider_filter=lambda value: value,
        )
    assert response.media_type == "text/csv"
    assert "close-package-2026-01-01-2026-01-31-aws.csv" in response.headers[
        "Content-Disposition"
    ]


@pytest.mark.asyncio
async def test_get_restatement_history_impl_rejects_excess_window() -> None:
    user = _user()
    db = _FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await get_restatement_history_impl(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            provider=None,
            response_format="json",
            user=user,
            db=db,  # type: ignore[arg-type]
            require_tenant_id=lambda u: u.tenant_id,  # type: ignore[return-value]
            normalize_provider_filter=lambda value: value,
            get_settings=lambda: SimpleNamespace(FOCUS_EXPORT_MAX_DAYS=31),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upsert_provider_invoice_impl_maps_validation_errors() -> None:
    user = _user()
    db = _FakeDB()
    payload = ProviderInvoiceUpsertRequest(
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        currency="USD",
        total_amount=100.0,
        invoice_number="INV-001",
        status="draft",
        notes=None,
    )
    with patch(
        "app.modules.reporting.api.v1.costs_reconciliation_routes.CostReconciliationService.upsert_invoice",
        new=AsyncMock(side_effect=ValueError("invalid invoice amount")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await upsert_provider_invoice_impl(
                request=_request(),
                payload=payload,
                user=user,
                db=db,  # type: ignore[arg-type]
                require_tenant_id=lambda u: u.tenant_id,  # type: ignore[return-value]
            )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_export_focus_v13_costs_csv_impl_streams_expected_rows() -> None:
    user = _user()
    db = _FakeDB()

    async def _rows(self, **_kwargs):
        _ = self
        yield {"BillingCurrency": "USD", "ServiceName": "=1+1"}

    with patch(
        "app.modules.reporting.api.v1.costs_reconciliation_routes.FocusV13ExportService.export_rows",
        new=_rows,
    ):
        response = await export_focus_v13_costs_csv_impl(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1),
            provider="aws",
            include_preliminary=False,
            user=user,
            db=db,  # type: ignore[arg-type]
            require_tenant_id=lambda u: u.tenant_id,  # type: ignore[return-value]
            normalize_provider_filter=lambda value: value,
            sanitize_csv_cell=lambda value: f"'{value}"
            if str(value).startswith("=")
            else str(value),
            get_settings=lambda: SimpleNamespace(FOCUS_EXPORT_MAX_DAYS=31),
        )

        collected: list[bytes] = []
        async for chunk in response.body_iterator:
            collected.append(chunk)
        csv_text = b"".join(collected).decode("utf-8")

    assert "BillingCurrency" in csv_text
    assert "'=1+1" in csv_text
