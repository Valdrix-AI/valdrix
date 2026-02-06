"""
Tests for Dunning Handler

Tests payment retry logic for failed subscriptions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.modules.governance.domain.jobs.handlers.dunning import DunningHandler


class TestDunningHandler:
    """Test DunningHandler execution logic."""
    
    @pytest.fixture
    def handler(self):
        """Create a DunningHandler instance."""
        return DunningHandler()
    
    @pytest.fixture
    def mock_job(self):
        """Create a mock BackgroundJob."""
        job = MagicMock()
        job.payload = {
            "subscription_id": str(uuid4()),
            "attempt": 1
        }
        return job
    
    @pytest.fixture
    def mock_db(self):
        """Create a mock AsyncSession."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_execute_successful_retry(self, handler, mock_job, mock_db):
        """Test successful payment retry."""
        # Patch at the module where it's imported (lazy import inside function)
        with patch(
            "app.modules.reporting.domain.billing.dunning_service.DunningService"
        ) as MockDunning:
            mock_service = AsyncMock()
            mock_service.retry_payment.return_value = {
                "status": "success",
                "charged_amount": 2900
            }
            MockDunning.return_value = mock_service
            
            result = await handler.execute(mock_job, mock_db)
            
            assert result["status"] == "success"
            assert result["attempt"] == 1
            assert result["charged_amount"] == 2900
    
    @pytest.mark.asyncio
    async def test_execute_failed_retry(self, handler, mock_job, mock_db):
        """Test failed payment retry."""
        with patch(
            "app.modules.reporting.domain.billing.dunning_service.DunningService"
        ) as MockDunning:
            mock_service = AsyncMock()
            mock_service.retry_payment.return_value = {
                "status": "failed",
                "error": "Card declined"
            }
            MockDunning.return_value = mock_service
            
            result = await handler.execute(mock_job, mock_db)
            
            assert result["status"] == "failed"
            assert result["error"] == "Card declined"
    
    @pytest.mark.asyncio
    async def test_execute_missing_subscription_id(self, handler, mock_db):
        """Test error when subscription_id is missing."""
        job = MagicMock()
        job.payload = {"attempt": 1}  # Missing subscription_id
        
        with pytest.raises(ValueError, match="subscription_id required"):
            await handler.execute(job, mock_db)
    
    @pytest.mark.asyncio
    async def test_execute_empty_payload(self, handler, mock_db):
        """Test error when payload is empty."""
        job = MagicMock()
        job.payload = {}
        
        with pytest.raises(ValueError, match="subscription_id required"):
            await handler.execute(job, mock_db)
    
    @pytest.mark.asyncio
    async def test_execute_none_payload(self, handler, mock_db):
        """Test error when payload is None."""
        job = MagicMock()
        job.payload = None
        
        with pytest.raises(ValueError, match="subscription_id required"):
            await handler.execute(job, mock_db)
    
    @pytest.mark.asyncio
    async def test_execute_increments_attempt(self, handler, mock_db):
        """Test that attempt number is included in result."""
        job = MagicMock()
        job.payload = {
            "subscription_id": str(uuid4()),
            "attempt": 3
        }
        
        with patch(
            "app.modules.reporting.domain.billing.dunning_service.DunningService"
        ) as MockDunning:
            mock_service = AsyncMock()
            mock_service.retry_payment.return_value = {"status": "success"}
            MockDunning.return_value = mock_service
            
            result = await handler.execute(job, mock_db)
            
            assert result["attempt"] == 3
    
    @pytest.mark.asyncio
    async def test_execute_default_attempt_is_one(self, handler, mock_db):
        """Test that default attempt is 1 when not specified."""
        job = MagicMock()
        job.payload = {
            "subscription_id": str(uuid4())
            # No attempt specified
        }
        
        with patch(
            "app.modules.reporting.domain.billing.dunning_service.DunningService"
        ) as MockDunning:
            mock_service = AsyncMock()
            mock_service.retry_payment.return_value = {"status": "success"}
            MockDunning.return_value = mock_service
            
            result = await handler.execute(job, mock_db)
            
            assert result["attempt"] == 1
