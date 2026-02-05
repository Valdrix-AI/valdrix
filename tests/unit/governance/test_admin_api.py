
import pytest
from fastapi import Request, HTTPException
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.governance.api.v1.admin import validate_admin_key, trigger_analysis, reconcile_tenant_costs
from app.shared.core.config import Settings

@pytest.mark.asyncio
async def test_validate_admin_key_missing():
    request = MagicMock(spec=Request)
    # Mock settings with no key
    with patch("app.modules.governance.api.v1.admin.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_API_KEY = None
        
        with pytest.raises(HTTPException) as exc:
            await validate_admin_key(request, x_admin_key="anything")
        assert exc.value.status_code == 503

@pytest.mark.asyncio
async def test_validate_admin_key_weak_prod():
    request = MagicMock(spec=Request)
    with patch("app.modules.governance.api.v1.admin.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_API_KEY = "weak"
        mock_settings.return_value.ENVIRONMENT = "production"
        
        with pytest.raises(HTTPException) as exc:
            await validate_admin_key(request, x_admin_key="weak")
        assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_validate_admin_key_invalid():
    request = MagicMock(spec=Request)
    request.url.path = "/admin"
    request.client.host = "1.2.3.4"
    
    with patch("app.modules.governance.api.v1.admin.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_API_KEY = "strong-key-for-testing-purposes-only"
        mock_settings.return_value.ENVIRONMENT = "production"
        
        with pytest.raises(HTTPException) as exc:
            await validate_admin_key(request, x_admin_key="wrong-key")
        assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_validate_admin_key_success():
    request = MagicMock(spec=Request)
    with patch("app.modules.governance.api.v1.admin.get_settings") as mock_settings:
        mock_settings.return_value.ADMIN_API_KEY = "strong-key-for-testing-purposes-only"
        
        result = await validate_admin_key(request, x_admin_key="strong-key-for-testing-purposes-only")
        assert result is True

@pytest.mark.asyncio
async def test_trigger_analysis_success():
    request = MagicMock(spec=Request)
    request.app.state.scheduler.daily_analysis_job = AsyncMock()
    
    resp = await trigger_analysis(request, True)
    assert resp["status"] == "triggered"
    request.app.state.scheduler.daily_analysis_job.assert_awaited_once()

@pytest.mark.asyncio
async def test_reconcile_tenant_costs_success(db):
    request = MagicMock(spec=Request)
    tenant_id = "123e4567-e89b-12d3-a456-426614174000"
    start_date = "2023-01-01"
    end_date = "2023-01-31"
    
    with patch("app.modules.reporting.domain.reconciliation.CostReconciliationService") as MockService:
        service = MockService.return_value
        service.compare_explorer_vs_cur = AsyncMock(return_value={"diff": 0})
        
        from uuid import UUID
        from datetime import date
        result = await reconcile_tenant_costs(
            request, 
            UUID(tenant_id), 
            date.fromisoformat(start_date), 
            date.fromisoformat(end_date), 
            db, 
            True
        )
        assert result["diff"] == 0
