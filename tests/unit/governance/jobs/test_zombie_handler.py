import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.zombie import ZombieScanHandler

@pytest.mark.asyncio
async def test_zombie_scan_handler():
    """Test zombie scan background job."""
    handler = ZombieScanHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = AsyncMock()
    
    with patch("app.modules.optimization.domain.service.ZombieService") as MockService:
        service = MockService.return_value
        # Mock results
        service.scan_for_tenant = AsyncMock(return_value={
            "ec2_idle": [{"id": "i-1", "provider": "aws"}],
            "total_monthly_waste": 50.0
        })
        
        res = await handler.execute(job, db)
        
        assert res["status"] == "completed"
        assert res["zombies_found"] == 1
        assert res["total_waste"] == 50.0
        assert len(res["details"]) == 1
        assert res["details"][0]["provider"] == "aws"
