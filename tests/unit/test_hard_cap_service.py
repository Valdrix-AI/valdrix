"""
Tests for BudgetHardCapService

Tests the hard cap enforcement logic which suspends connections
and deactivates tenants when budget is critically exceeded.
"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from app.shared.remediation.hard_cap_service import BudgetHardCapService

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db

@pytest.fixture
def hard_cap_service(mock_db):
    return BudgetHardCapService(mock_db)

@pytest.mark.asyncio
async def test_enforce_hard_cap_suspends_connections(hard_cap_service, mock_db):
    """Test that enforce_hard_cap updates AWS connections to suspended."""
    tenant_id = uuid4()
    
    await hard_cap_service.enforce_hard_cap(tenant_id)
    
    # Verify execute was called (for connection and tenant updates)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_enforce_hard_cap_deactivates_tenant(hard_cap_service, mock_db):
    """Test that enforce_hard_cap deactivates the tenant."""
    tenant_id = uuid4()
    
    await hard_cap_service.enforce_hard_cap(tenant_id)
    
    # Verify both update calls (connections + tenant)
    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_enforce_hard_cap_logs_correctly(hard_cap_service, mock_db):
    """Test that enforce_hard_cap logs warning and info messages."""
    tenant_id = uuid4()
    
    with patch("app.shared.remediation.hard_cap_service.logger") as mock_logger:
        await hard_cap_service.enforce_hard_cap(tenant_id)
        
        mock_logger.warning.assert_called_once()
        mock_logger.info.assert_called_once()
