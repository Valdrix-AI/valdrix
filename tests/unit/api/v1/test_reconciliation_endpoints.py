from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.shared.core.auth import CurrentUser, UserRole, get_current_user
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_close_package_endpoint_json(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="close-json@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.generate_close_package",
            new=AsyncMock(
                return_value={
                    "close_status": "ready",
                    "integrity_hash": "abc123",
                    "csv": "section,key,value\nmeta,tenant_id,x\n",
                }
            ),
        ) as mock_generate:
            response = await async_client.get(
                "/api/v1/costs/reconciliation/close-package",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert response.status_code == 200
            assert response.json()["close_status"] == "ready"
            assert response.json()["integrity_hash"] == "abc123"
            mock_generate.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_package_endpoint_csv(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="close-csv@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.generate_close_package",
            new=AsyncMock(
                return_value={
                    "close_status": "ready",
                    "integrity_hash": "abc123",
                    "csv": "section,key,value\nmeta,tenant_id,x\n",
                }
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/reconciliation/close-package",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "response_format": "csv",
                },
            )
            assert response.status_code == 200
            assert "text/csv" in response.headers["content-type"]
            assert "attachment; filename=" in response.headers.get(
                "content-disposition", ""
            )
            assert "section,key,value" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_package_endpoint_returns_conflict(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="close-conflict@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.generate_close_package",
            new=AsyncMock(
                side_effect=ValueError(
                    "Cannot generate final close package while preliminary records exist in the selected period."
                )
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/reconciliation/close-package",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert response.status_code == 409
            assert "preliminary records exist" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_restatement_history_endpoint_json_and_csv(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="restatement@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.get_restatement_history",
            new=AsyncMock(
                side_effect=[
                    {
                        "restatement_count": 1,
                        "entries": [{"service": "Zendesk"}],
                        "net_delta_usd": 5.0,
                        "absolute_delta_usd": 5.0,
                    },
                    {
                        "restatement_count": 1,
                        "entries": [{"service": "Zendesk"}],
                        "net_delta_usd": 5.0,
                        "absolute_delta_usd": 5.0,
                        "csv": "usage_date,recorded_at,service\n2026-01-01,2026-02-01T00:00:00+00:00,Zendesk\n",
                    },
                ]
            ),
        ):
            json_response = await async_client.get(
                "/api/v1/costs/reconciliation/restatements",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert json_response.status_code == 200
            assert json_response.json()["restatement_count"] == 1

            csv_response = await async_client.get(
                "/api/v1/costs/reconciliation/restatements",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "response_format": "csv",
                },
            )
            assert csv_response.status_code == 200
            assert "text/csv" in csv_response.headers["content-type"]
            assert "attachment; filename=" in csv_response.headers.get(
                "content-disposition", ""
            )
            assert "usage_date,recorded_at,service" in csv_response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_restatement_runs_endpoint_json_and_csv(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="restatement-runs@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.get_restatement_runs",
            new=AsyncMock(
                side_effect=[
                    {
                        "run_count": 1,
                        "runs": [{"ingestion_batch_id": "abc", "entry_count": 3}],
                    },
                    {
                        "run_count": 1,
                        "runs": [{"ingestion_batch_id": "abc", "entry_count": 3}],
                        "csv": "ingestion_batch_id,entry_count\nabc,3\n",
                    },
                ]
            ),
        ):
            json_response = await async_client.get(
                "/api/v1/costs/reconciliation/restatement-runs",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert json_response.status_code == 200
            assert json_response.json()["run_count"] == 1

            csv_response = await async_client.get(
                "/api/v1/costs/reconciliation/restatement-runs",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "response_format": "csv",
                },
            )
            assert csv_response.status_code == 200
            assert "text/csv" in csv_response.headers["content-type"]
            assert "attachment; filename=" in csv_response.headers.get(
                "content-disposition", ""
            )
            assert "ingestion_batch_id" in csv_response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_close_package_endpoint_rejects_invalid_date_order(
    async_client, app
) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="close-invalid-window@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = await async_client.get(
            "/api/v1/costs/reconciliation/close-package",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )
        assert response.status_code == 400
        assert "start_date must be <= end_date" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_restatement_history_rejects_max_window(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="restatement-window-limit@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.get_settings",
            return_value=SimpleNamespace(FOCUS_EXPORT_MAX_DAYS=1),
        ):
            response = await async_client.get(
                "/api/v1/costs/reconciliation/restatements",
                params={"start_date": "2026-01-01", "end_date": "2026-01-03"},
            )
        assert response.status_code == 400
        assert "Date window exceeds export limit" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_restatement_runs_rejects_invalid_date_order(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="restatement-runs-invalid-window@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = await async_client.get(
            "/api/v1/costs/reconciliation/restatement-runs",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )
        assert response.status_code == 400
        assert "start_date must be <= end_date" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_list_provider_invoices_returns_transformed_payload(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-list@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    invoice = SimpleNamespace(
        id=uuid4(),
        provider="aws",
        period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
        invoice_number="INV-2026-01",
        currency="USD",
        total_amount=125.5,
        total_amount_usd=125.5,
        status="draft",
        notes="initial import",
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.list_invoices",
            new=AsyncMock(return_value=[invoice]),
        ) as mock_list:
            response = await async_client.get(
                "/api/v1/costs/reconciliation/invoices",
                params={"provider": "aws"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body[0]["provider"] == "aws"
        assert body[0]["invoice_number"] == "INV-2026-01"
        assert body[0]["total_amount_usd"] == 125.5
        mock_list.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_upsert_provider_invoice_success(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-upsert@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    invoice = SimpleNamespace(
        id=uuid4(),
        provider="aws",
        period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 1, 31, tzinfo=timezone.utc),
        invoice_number="INV-2026-01",
        currency="USD",
        total_amount=100.0,
        total_amount_usd=100.0,
        status="posted",
        notes="ok",
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostReconciliationService.upsert_invoice",
                new=AsyncMock(return_value=invoice),
            ),
            patch(
                "app.modules.reporting.api.v1.costs.AuditLogger.log",
                new=AsyncMock(return_value=None),
            ),
        ):
            response = await async_client.post(
                "/api/v1/costs/reconciliation/invoices",
                json={
                    "provider": "aws",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "currency": "USD",
                    "total_amount": 100.0,
                    "invoice_number": "INV-2026-01",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["invoice"]["provider"] == "aws"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_upsert_provider_invoice_rejects_invalid_window(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-upsert-invalid-window@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = await async_client.post(
            "/api/v1/costs/reconciliation/invoices",
            json={
                "provider": "aws",
                "start_date": "2026-02-01",
                "end_date": "2026-01-01",
                "currency": "USD",
                "total_amount": 10.0,
            },
        )
        assert response.status_code == 400
        assert "start_date must be <= end_date" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_upsert_provider_invoice_maps_service_validation_error(
    async_client, app
) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-upsert-service-error@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch(
            "app.modules.reporting.api.v1.costs.CostReconciliationService.upsert_invoice",
            new=AsyncMock(side_effect=ValueError("invalid invoice payload")),
        ):
            response = await async_client.post(
                "/api/v1/costs/reconciliation/invoices",
                json={
                    "provider": "aws",
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "currency": "USD",
                    "total_amount": 10.0,
                },
            )
        assert response.status_code == 422
        assert "invalid invoice payload" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_update_provider_invoice_status_success_and_not_found(
    async_client, app
) -> None:
    tenant_id = uuid4()
    invoice_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-status@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostReconciliationService.update_invoice_status",
                new=AsyncMock(
                    side_effect=[SimpleNamespace(status="posted"), None]
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs.AuditLogger.log",
                new=AsyncMock(return_value=None),
            ),
        ):
            success_response = await async_client.patch(
                f"/api/v1/costs/reconciliation/invoices/{invoice_id}",
                json={"status": "posted"},
            )
            missing_response = await async_client.patch(
                f"/api/v1/costs/reconciliation/invoices/{invoice_id}",
                json={"status": "posted"},
            )

        assert success_response.status_code == 200
        assert success_response.json()["invoice_status"] == "posted"
        assert missing_response.status_code == 404
        assert "Invoice not found" in missing_response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_delete_provider_invoice_success_and_not_found(async_client, app) -> None:
    tenant_id = uuid4()
    invoice_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="invoice-delete@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostReconciliationService.delete_invoice",
                new=AsyncMock(side_effect=[True, False]),
            ),
            patch(
                "app.modules.reporting.api.v1.costs.AuditLogger.log",
                new=AsyncMock(return_value=None),
            ),
        ):
            success_response = await async_client.delete(
                f"/api/v1/costs/reconciliation/invoices/{invoice_id}"
            )
            missing_response = await async_client.delete(
                f"/api/v1/costs/reconciliation/invoices/{invoice_id}"
            )

        assert success_response.status_code == 200
        assert success_response.json()["status"] == "deleted"
        assert missing_response.status_code == 404
        assert "Invoice not found" in missing_response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_export_focus_endpoint_validations_and_stream(async_client, app) -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        tenant_id=tenant_id,
        email="focus-export@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        invalid_range = await async_client.get(
            "/api/v1/costs/export/focus",
            params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )
        assert invalid_range.status_code == 400
        assert "start_date must be <= end_date" in invalid_range.json()["error"]

        with patch(
            "app.modules.reporting.api.v1.costs.get_settings",
            return_value=SimpleNamespace(FOCUS_EXPORT_MAX_DAYS=1),
        ):
            too_large = await async_client.get(
                "/api/v1/costs/export/focus",
                params={"start_date": "2026-01-01", "end_date": "2026-01-03"},
            )
        assert too_large.status_code == 400
        assert "Date window exceeds export limit" in too_large.json()["error"]

        async def _rows(self, **kwargs):  # noqa: ANN001
            yield {"BilledCost": "12.5", "BillingAccountId": "acct-1"}

        with patch(
            "app.modules.reporting.api.v1.costs.FocusV13ExportService.export_rows",
            new=_rows,
        ):
            ok = await async_client.get(
                "/api/v1/costs/export/focus",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-02",
                    "provider": "aws",
                    "include_preliminary": "true",
                },
            )

        assert ok.status_code == 200
        assert "text/csv" in ok.headers["content-type"]
        assert "BilledCost" in ok.text
        assert "12.5" in ok.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
