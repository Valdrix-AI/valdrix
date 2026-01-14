import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.services.zombies.detector import ZombieDetector, RemediationService
from app.models.remediation import RemediationAction, RemediationStatus, RemediationRequest

# --- ZombieDetector Tests ---

@pytest.mark.asyncio
async def test_detect_zombies_aggregation():
    """Verify scan_all aggregates results from plugins."""
    detector = ZombieDetector()
    
    # Mock plugins
    mock_plugin1 = AsyncMock()
    mock_plugin1.category_key = "unused_volumes"
    mock_plugin1.scan.return_value = [{"id": "vol-1", "monthly_cost": 10.0}]
    
    mock_plugin2 = AsyncMock()
    mock_plugin2.category_key = "idle_instances"
    mock_plugin2.scan.return_value = [{"id": "i-1", "monthly_cost": 50.5}]
    
    detector.plugins = [mock_plugin1, mock_plugin2]
    
    results = await detector.scan_all()
    
    assert results["total_monthly_waste"] == 60.5
    assert len(results["unused_volumes"]) == 1
    assert len(results["idle_instances"]) == 1
    assert "error" not in results

@pytest.mark.asyncio
async def test_detect_zombies_partial_failure():
    """Verify scan_all continues if one plugin fails."""
    detector = ZombieDetector()
    
    mock_plugin1 = AsyncMock()
    mock_plugin1.category_key = "good_plugin"
    mock_plugin1.scan.return_value = [{"id": "res-1", "monthly_cost": 10}]
    
    mock_plugin2 = AsyncMock()
    mock_plugin2.category_key = "bad_plugin"
    mock_plugin2.scan.side_effect = Exception("API Error")
    
    detector.plugins = [mock_plugin1, mock_plugin2]
    
    results = await detector.scan_all()
    
    assert results["total_monthly_waste"] == 10.0
    assert len(results["good_plugin"]) == 1
    assert results["bad_plugin"] == [] # Should be empty list/handled

# --- RemediationService Tests ---

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # The result of await db.execute(...) must be a synchronous MagicMock
    result_mock = MagicMock()
    db.execute.return_value = result_mock
    
    # Configure default behaviors
    result_mock.scalars.return_value.all.return_value = []
    result_mock.scalar_one_or_none.return_value = None
    
    return db

@pytest.fixture
def service(mock_db):
    return RemediationService(mock_db)

@pytest.mark.asyncio
async def test_create_remediation_request(service, mock_db):
    tenant_id = uuid4()
    user_id = uuid4()
    
    req = await service.create_request(
        tenant_id=tenant_id,
        user_id=user_id,
        resource_id="vol-123",
        resource_type="ec2_volume",
        action=RemediationAction.DELETE_VOLUME,
        estimated_savings=20.0
    )
    
    assert req.status == RemediationStatus.PENDING
    assert req.resource_id == "vol-123"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_approve_request(service, mock_db):
    req = RemediationRequest(
        id=uuid4(),
        tenant_id=uuid4(), 
        status=RemediationStatus.PENDING
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = req
    
    approved = await service.approve(req.id, req.tenant_id, uuid4())
    
    assert approved.status == RemediationStatus.APPROVED
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_execute_request_success(service, mock_db):
    """Test execution of DELETE_VOLUME action."""
    req = RemediationRequest(
        id=uuid4(),
        tenant_id=uuid4(),
        resource_id="vol-123",
        action=RemediationAction.DELETE_VOLUME,
        status=RemediationStatus.APPROVED,
        create_backup=False
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = req
    
    # Mock AWS client
    mock_ec2 = AsyncMock()
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ec2
    
    with patch.object(service, 'session', mock_session):
        await service.execute(req.id, req.tenant_id)
        
        mock_ec2.delete_volume.assert_called_once_with(VolumeId="vol-123")
        assert req.status == RemediationStatus.COMPLETED
