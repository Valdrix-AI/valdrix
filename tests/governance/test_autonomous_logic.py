import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.shared.remediation.autonomous import AutonomousRemediationEngine
from app.models.remediation import RemediationAction

@pytest.mark.asyncio
async def test_autonomous_dry_run_safety():
    """Verify that dry_run=True NEVER executes actions."""
    
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = False # Default is False (Dry run)
    
    # Mock remediation service
    mock_service = AsyncMock()
    # Mock existing request check to return None (no duplicate)
    # create a synchronous Mock for the Result object
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result
    
    # Process a high confidence candidate
    await engine._process_candidate(
        service=mock_service,
        resource_id="vol-123",
        resource_type="ebs_volume",
        action=RemediationAction.DELETE_VOLUME,
        savings=10.0,
        confidence=1.0, # 100% confidence
        reason="Test candidate"
    )
    
    # Should create request
    mock_service.create_request.assert_awaited_once()
    
    # Should NOT approve or execute
    mock_service.approve.assert_not_awaited()
    mock_service.execute.assert_not_awaited()

@pytest.mark.asyncio
async def test_autonomous_auto_pilot_execution():
    """Verify that auto-pilot executes high confidence items."""
    
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = True # Enable Auto-Pilot
    
    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result
    
    # Process high confidence (above 0.95 threshold)
    await engine._process_candidate(
        service=mock_service, 
        resource_id="snap-123",
        resource_type="ebs_snapshot",
        action=RemediationAction.DELETE_SNAPSHOT,
        savings=5.0,
        confidence=0.99,
        reason="Test candidate"
    )
    
    # Should execute
    mock_service.create_request.assert_awaited_once()
    mock_service.approve.assert_awaited_once()
    mock_service.execute.assert_awaited_once()

@pytest.mark.asyncio
async def test_autonomous_low_confidence_safety():
    """Verify low confidence items are NOT auto-executed even in auto-pilot."""
    
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = True # Enable Auto-Pilot
    
    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result
    
    # Process low confidence (below 0.95)
    await engine._process_candidate(
        service=mock_service, 
        resource_id="vol-sus",
        resource_type="ebs_volume",
        action=RemediationAction.DELETE_VOLUME,
        savings=10.0,
        confidence=0.80,
        reason="Test candidate"
    )
    
    # Should create request but NOT execute
    mock_service.create_request.assert_awaited_once()
    mock_service.execute.assert_not_awaited()
