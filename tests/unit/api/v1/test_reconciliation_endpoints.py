from unittest.mock import AsyncMock, patch
from uuid import uuid4

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
