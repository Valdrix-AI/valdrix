"""
Tests for Scheduler Processors - Analysis and Savings
No existing tests for these modules.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date

from app.modules.governance.domain.scheduler.processors import AnalysisProcessor, SavingsProcessor


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_tenant():
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Tenant"
    return tenant


class TestAnalysisProcessor:
    """Tests for AnalysisProcessor."""

    def test_init(self):
        """Test processor initialization."""
        processor = AnalysisProcessor()
        assert processor.settings is not None

    @pytest.mark.asyncio
    async def test_process_tenant_success(self, mock_db, mock_tenant):
        """Test processing tenant analysis."""
        processor = AnalysisProcessor()
        
        # Mock dependencies
        with patch("app.modules.governance.domain.scheduler.processors.MultiTenantAWSAdapter") as mock_adapter, \
             patch("app.modules.governance.domain.scheduler.processors.ZombieDetector") as mock_detector, \
             patch("app.modules.governance.domain.scheduler.processors.LLMFactory") as mock_factory:
            
            mock_adapter_instance = AsyncMock()
            mock_adapter_instance.get_tenant_costs.return_value = []
            mock_adapter.return_value = mock_adapter_instance
            
            mock_detector_instance = AsyncMock()
            mock_detector_instance.scan.return_value = []
            mock_detector.return_value = mock_detector_instance
            
            mock_llm = MagicMock()
            mock_factory.create.return_value = mock_llm
            
            start_date = date.today()
            end_date = date.today()
            
            result = await processor.process_tenant(
                mock_db, mock_tenant, start_date, end_date
            )
            
            # Should complete without error
            assert result is None or isinstance(result, dict)


class TestSavingsProcessor:
    """Tests for SavingsProcessor."""

    def test_map_action_to_enum_delete_volume(self):
        """Test action mapping for delete volume."""
        processor = SavingsProcessor()
        # Actual implementation uses substring matching
        result = processor._map_action_to_enum("delete volume ebs")
        assert result is not None

    def test_map_action_to_enum_delete_snapshot(self):
        """Test action mapping for delete snapshot."""
        processor = SavingsProcessor()
        result = processor._map_action_to_enum("delete snapshot backup")
        assert result is not None

    def test_map_action_to_enum_unknown(self):
        """Test action mapping for unknown action returns None."""
        processor = SavingsProcessor()
        result = processor._map_action_to_enum("UNKNOWN_ACTION")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_recommendations_empty(self, mock_db):
        """Test processing empty recommendations."""
        processor = SavingsProcessor()
        
        mock_result = MagicMock()
        mock_result.recommendations = []
        
        tenant_id = uuid4()
        
        result = await processor.process_recommendations(
            mock_db, tenant_id, mock_result
        )
        
        # Should handle empty recommendations gracefully
        assert result is None or isinstance(result, list)

    @pytest.mark.asyncio
    async def test_process_recommendations_with_autonomous_ready(self, mock_db):
        """Test processing recommendations with autonomous_ready items."""
        processor = SavingsProcessor()
        
        mock_recommendation = MagicMock()
        mock_recommendation.action = "delete volume ebs"
        mock_recommendation.resource = "vol-123"
        mock_recommendation.resource_type = "ebs_volume"
        mock_recommendation.confidence = "high"
        mock_recommendation.estimated_savings = "$10.00/month"
        mock_recommendation.autonomous_ready = True
        
        mock_result = MagicMock()
        mock_result.recommendations = [mock_recommendation]
        
        tenant_id = uuid4()
        
        # Patch in the module where it's imported
        with patch("app.modules.optimization.domain.remediation_service.RemediationService") as mock_service:
            mock_service_instance = AsyncMock()
            mock_service_instance.create_request.return_value = MagicMock(id=uuid4())
            mock_service_instance.approve = AsyncMock()
            mock_service_instance.execute = AsyncMock()
            mock_service.return_value = mock_service_instance
            
            await processor.process_recommendations(
                mock_db, tenant_id, mock_result
            )

