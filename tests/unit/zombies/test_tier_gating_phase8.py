import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
from app.modules.optimization.domain.service import ZombieService
from app.shared.core.pricing import PricingTier

@pytest.mark.asyncio
async def test_zombie_service_field_masking_starter():
    """Verify that Starter tier users see masked GPU and Owner fields."""
    db = AsyncMock()
    tenant_id = uuid4()
    
    # Mock tenant tier as STARTER
    with patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        mock_tier.return_value = PricingTier.STARTER
        # Mock connections
        mock_result_aws = MagicMock()
        mock_result_empty = MagicMock()
        mock_result_aws.scalars.return_value.all.return_value = []
        mock_result_empty.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result_aws # Initial default
        
        service = ZombieService(db)
        
        # We need to mock a result from a detector to test the masking loop
        # Instead of running a full scan, we can mock the detector output
        
        mock_items = [
            {"id": "res-1", "monthly_cost": 100, "owner": "real-owner", "is_gpu": True},
            {"id": "res-2", "monthly_cost": 50, "owner": "other-owner", "is_gpu": False}
        ]
        
        mock_detector = MagicMock()
        mock_detector.scan_all = AsyncMock(return_value={
            "idle_instances": mock_items
        })
        mock_detector.provider_name = "aws"
        
        with patch("app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector", return_value=mock_detector):
            # We need to have at least one connection to trigger the loop
            connection = MagicMock()
            connection.tenant_id = tenant_id
            
            mock_result_aws = MagicMock()
            mock_result_aws.scalars.return_value.all.return_value = [connection]
            mock_result_empty = MagicMock()
            mock_result_empty.scalars.return_value.all.return_value = []
            
            # 3 calls: AWS, Azure, GCP. Only return connection for AWS.
            db.execute.side_effect = [mock_result_aws, mock_result_empty, mock_result_empty]
            
            results = await service.scan_for_tenant(tenant_id)
            
            # Verify results are masked
            idle_instances = results["idle_instances"]
            assert len(idle_instances) == 2
            for item in idle_instances:
                assert item["owner"] == "Upgrade to Growth"
                assert item["is_gpu"] == "Upgrade to Growth"

@pytest.mark.asyncio
async def test_zombie_service_no_masking_pro():
    """Verify that Pro tier users see real GPU and Owner fields."""
    db = AsyncMock()
    tenant_id = uuid4()
    
    # Mock tenant tier as PRO
    # Mock tenant tier as PRO
    with patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        mock_tier.return_value = PricingTier.PRO
        
        connection = MagicMock()
        connection.tenant_id = tenant_id
        
        mock_result_aws = MagicMock()
        mock_result_aws.scalars.return_value.all.return_value = [connection]
        mock_result_empty = MagicMock()
        mock_result_empty.scalars.return_value.all.return_value = []
        
        # 3 calls: AWS, Azure, GCP
        db.execute.side_effect = [mock_result_aws, mock_result_empty, mock_result_empty]
        
        mock_items = [
            {"id": "res-1", "monthly_cost": 100, "owner": "real-owner", "is_gpu": True}
        ]
        
        mock_detector = MagicMock()
        mock_detector.scan_all = AsyncMock(return_value={
            "idle_instances": mock_items
        })
        mock_detector.provider_name = "aws"
        
        with patch("app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector", return_value=mock_detector):
            service = ZombieService(db)
            results = await service.scan_for_tenant(tenant_id)
            
            item = results["idle_instances"][0]
            assert item["owner"] == "real-owner"
            assert item["is_gpu"] is True

@pytest.mark.asyncio
async def test_remediation_service_iac_gating_starter():
    """Verify that Starter tier users cannot generate IaC plans."""
    from app.modules.optimization.domain.remediation_service import RemediationService
    db = AsyncMock()
    tenant_id = uuid4()
    
    # Mock tenant tier as STARTER
    # Mock tenant tier as STARTER
    with patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        mock_tier.return_value = PricingTier.STARTER
        service = RemediationService(db)
        request = MagicMock()
        
        plan = await service.generate_iac_plan(request, tenant_id)
        assert "unlock IaC plans" in plan

@pytest.mark.asyncio
async def test_remediation_service_iac_allowed_pro():
    """Verify that Pro tier users can generate IaC plans."""
    from app.modules.optimization.domain.remediation_service import RemediationService
    db = AsyncMock()
    tenant_id = uuid4()
    
    # Mock tenant tier as PRO
    with patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier:
        mock_tier.return_value = PricingTier.PRO
        service = RemediationService(db)
        request = MagicMock()
        request.resource_id = "res-id"
        request.provider = "aws"
        request.resource_type = "EC2 Instance"
        request.estimated_monthly_savings = 100
        request.action = MagicMock()
        request.action.value = "terminate"
        
        plan = await service.generate_iac_plan(request, tenant_id)
        assert "Valdrix GitOps Remediation Plan" in plan
        assert "res-id" in plan
