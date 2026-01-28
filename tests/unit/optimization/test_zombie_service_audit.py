import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from app.modules.optimization.domain.service import ZombieService
from app.models.aws_connection import AWSConnection
from app.shared.core.pricing import PricingTier

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def tenant_id():
    return uuid4()

@pytest.mark.asyncio
async def test_scan_for_tenant_no_connections(mock_db, tenant_id):
    service = ZombieService(mock_db)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_res
    
    result = await service.scan_for_tenant(tenant_id)
    
    assert result["resources"] == {}
    assert result["total_monthly_waste"] == 0.0
    assert "No cloud connections found" in result["error"]

@pytest.mark.asyncio
async def test_scan_for_tenant_success(mock_db, tenant_id):
    service = ZombieService(mock_db)
    
    # Mock AWS connection
    conn = MagicMock(spec=AWSConnection)
    conn.id = uuid4()
    conn.tenant_id = tenant_id
    conn.name = "Prod-AWS"
    
    # Mock sequence: AWS, Azure, GCP
    mock_res_aws = MagicMock()
    mock_res_aws.scalars.return_value.all.return_value = [conn]
    
    mock_res_empty = MagicMock()
    mock_res_empty.scalars.return_value.all.return_value = []
    
    mock_db.execute.side_effect = [mock_res_aws, mock_res_empty, mock_res_empty]
    
    # Mock detector
    mock_detector = AsyncMock()
    mock_detector.provider_name = "aws"
    mock_detector.scan_all.return_value = {
        "unattached_volumes": [{"resource_id": "vol-1", "monthly_cost": 10.0}]
    }
    
    with patch("app.modules.optimization.domain.service.ZombieDetectorFactory.get_detector", return_value=mock_detector):
        with patch("app.shared.core.pricing.get_tenant_tier", return_value=PricingTier.FREE):
            # Mock metrics
            with patch("app.shared.core.ops_metrics.SCAN_LATENCY") as mock_latency:
                result = await service.scan_for_tenant(tenant_id)
                
                assert result["total_monthly_waste"] == 10.0
                assert len(result["unattached_volumes"]) == 1
                assert result["unattached_volumes"][0]["resource_id"] == "vol-1"

@pytest.mark.asyncio
async def test_scan_for_tenant_timeout(mock_db, tenant_id):
    service = ZombieService(mock_db)
    
    conn = MagicMock()
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [conn]
    mock_db.execute.return_value = mock_res
    
    async def slow_scan(*args, **kwargs):
        await asyncio.sleep(0.1)
        return {}

    with patch("app.modules.optimization.domain.service.ZombieDetectorFactory.get_detector") as mock_factory:
        mock_detector = AsyncMock()
        mock_detector.provider_name = "aws"
        mock_detector.scan_all.side_effect = slow_scan
        mock_factory.return_value = mock_detector
        
        with patch("app.shared.core.pricing.get_tenant_tier", return_value=PricingTier.FREE):
            with patch("app.shared.core.ops_metrics.SCAN_TIMEOUTS") as mock_timeouts:
                # Use a very short timeout for testing
                with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                    result = await service.scan_for_tenant(tenant_id)
                    assert result["scan_timeout"] is True
                    assert result["partial_results"] is True
