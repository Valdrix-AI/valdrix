
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.zombie import ZombieScanHandler
from app.models.background_job import BackgroundJob

@pytest.mark.asyncio
async def test_execute_missing_tenant(db):
    handler = ZombieScanHandler()
    job = BackgroundJob(tenant_id=None)
    
    with pytest.raises(ValueError, match="tenant_id required"):
        await handler.execute(job, db)

@pytest.mark.asyncio
async def test_execute_success(db):
    handler = ZombieScanHandler()
    job = BackgroundJob(
        tenant_id=uuid4(), 
        payload={"regions": ["us-east-1"], "analyze": True}
    )
    
    mock_results = {
        "ec2_zombies": [{"id": "i-123", "provider": "aws"}],
        "rds_zombies": [],
        "total_monthly_waste": 50.0
    }
    
    with patch("app.modules.optimization.domain.service.ZombieService") as MockService:
        service = MockService.return_value
        service.scan_for_tenant = AsyncMock(return_value=mock_results)
        
        result = await handler.execute(job, db)
        
        assert result["status"] == "completed"
        assert result["zombies_found"] == 1
        assert result["total_waste"] == 50.0
        assert result["details"][0]["provider"] == "aws"
        
        # Verify arguments passed to scan
        service.scan_for_tenant.assert_awaited_with(
            tenant_id=job.tenant_id,
            region=["us-east-1"],
            analyze=True,
            on_category_complete=ANY
        )

@pytest.mark.asyncio
async def test_execute_checkpoint(db):
    handler = ZombieScanHandler()
    job = BackgroundJob(tenant_id=uuid4(), payload={})
    
    with patch("app.modules.optimization.domain.service.ZombieService") as MockService:
        service = MockService.return_value
        
        # Simulate service execution calling the callback
        async def mock_scan(on_category_complete, **kwargs):
            await on_category_complete("test_cat", ["item1"])
            return {"total_monthly_waste": 10}
            
        service.scan_for_tenant = AsyncMock(side_effect=mock_scan)
        
        await handler.execute(job, db)
        
        assert job.payload["partial_scan"]["test_cat"] == ["item1"]

@pytest.mark.asyncio
async def test_execute_skipped_no_results(db):
    handler = ZombieScanHandler()
    job = BackgroundJob(tenant_id=uuid4())
    
    with patch("app.modules.optimization.domain.service.ZombieService") as MockService:
        service = MockService.return_value
        service.scan_for_tenant = AsyncMock(return_value={"error": "no connections"})
        
        result = await handler.execute(job, db)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_connections_found"
