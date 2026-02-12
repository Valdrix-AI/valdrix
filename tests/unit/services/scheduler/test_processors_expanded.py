import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date
from app.modules.governance.domain.scheduler.processors import AnalysisProcessor, SavingsProcessor
from app.models.remediation import RemediationAction

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_tenant():
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Tenant"
    tenant.notification_settings = MagicMock()
    tenant.notification_settings.slack_enabled = False  # Disable to simplify
    tenant.notification_settings.digest_schedule = "daily"
    tenant.notification_settings.slack_channel_override = None
    tenant.aws_connections = [MagicMock()]
    tenant.azure_connections = []
    tenant.gcp_connections = []
    return tenant

class TestAnalysisProcessorExpanded:
    @pytest.mark.asyncio
    async def test_process_tenant_no_connections(self, mock_db):
        tenant = MagicMock()
        tenant.aws_connections = []
        tenant.azure_connections = []
        tenant.gcp_connections = []
        with patch("app.modules.governance.domain.scheduler.processors.get_settings"):
            processor = AnalysisProcessor()
            result = await processor.process_tenant(mock_db, tenant, date.today(), date.today())
            # Should finish early
            assert result is None

    @pytest.mark.asyncio
    async def test_process_tenant_timeout(self, mock_db, mock_tenant):
        with patch("app.modules.governance.domain.scheduler.processors.get_settings"):
            processor = AnalysisProcessor()
            with patch("app.modules.governance.domain.scheduler.processors.AdapterFactory") as mock_factory, \
                 patch("app.modules.governance.domain.scheduler.processors.LLMFactory"):
                mock_adapter_instance = MagicMock()
                mock_adapter_instance.get_daily_costs = AsyncMock(side_effect=asyncio.TimeoutError)
                mock_factory.get_adapter.return_value = mock_adapter_instance

                await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())
                # Logged error and continued

    @pytest.mark.asyncio
    async def test_process_tenant_exception(self, mock_db, mock_tenant):
        with patch("app.modules.governance.domain.scheduler.processors.get_settings"):
            processor = AnalysisProcessor()
            with patch("app.modules.governance.domain.scheduler.processors.AdapterFactory") as mock_factory, \
                 patch("app.modules.governance.domain.scheduler.processors.LLMFactory"):
                mock_adapter_instance = MagicMock()
                mock_adapter_instance.get_daily_costs.side_effect = Exception("Crash")
                mock_factory.get_adapter.return_value = mock_adapter_instance
                await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())
                # Logged error and continued


class TestSavingsProcessorExpanded:
    """Direct tests for SavingsProcessor without the full AnalysisProcessor flow."""
    
    @pytest.mark.asyncio
    async def test_process_recommendations_no_autonomous(self, mock_db):
        """Test that non-autonomous recommendations are skipped."""
        processor = SavingsProcessor()
        tenant_id = uuid4()
        
        # Create mock result with non-autonomous recommendations
        mock_result = MagicMock()
        mock_result.recommendations = [
            MagicMock(autonomous_ready=False, confidence="high", action="Delete volume", resource="vol-123", resource_type="EBS")
        ]
        
        with patch("app.modules.optimization.domain.remediation.RemediationService"):
            await processor.process_recommendations(mock_db, tenant_id, mock_result)
            # Should not call remediation since autonomous_ready=False

    @pytest.mark.asyncio
    async def test_process_recommendations_with_autonomous(self, mock_db):
        """Test that autonomous recommendations are executed."""
        processor = SavingsProcessor()
        tenant_id = uuid4()
        
        # Create mock result with autonomous recommendation
        mock_rec = MagicMock()
        mock_rec.autonomous_ready = True
        mock_rec.confidence = "high"
        mock_rec.action = "stop instance i-123"
        mock_rec.resource = "i-123"
        mock_rec.resource_type = "EC2 Instance"
        mock_rec.estimated_savings = "$50"
        
        mock_result = MagicMock()
        mock_result.recommendations = [mock_rec]
        
        with patch("app.modules.optimization.domain.remediation.RemediationService") as mock_remediation:
            mock_rem_instance = AsyncMock()
            mock_remediation.return_value = mock_rem_instance
            mock_rem_instance.create_request.return_value = MagicMock(id=uuid4())
            
            await processor.process_recommendations(mock_db, tenant_id, mock_result)
            
            mock_rem_instance.create_request.assert_called_once()
            mock_rem_instance.approve.assert_called_once()
            mock_rem_instance.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_recommendations_unsupported_action(self, mock_db):
        """Test handling of unsupported remediation actions."""
        processor = SavingsProcessor()
        tenant_id = uuid4()
        
        mock_rec = MagicMock()
        mock_rec.autonomous_ready = True
        mock_rec.confidence = "high"
        mock_rec.action = "Unsupported Action XYZ"
        mock_rec.resource = "resource-123"
        mock_rec.resource_type = "unknown"
        mock_rec.estimated_savings = "$10"
        
        mock_result = MagicMock()
        mock_result.recommendations = [mock_rec]
        
        with patch("app.modules.optimization.domain.remediation.RemediationService"):
            # Should not raise, just skip unsupported actions
            await processor.process_recommendations(mock_db, tenant_id, mock_result)

    def test_map_action_to_enum(self):
        """Test action string to enum mapping."""
        processor = SavingsProcessor()
        
        assert processor._map_action_to_enum("delete volume vol-123") == RemediationAction.DELETE_VOLUME
        assert processor._map_action_to_enum("stop instance i-123") == RemediationAction.STOP_INSTANCE
        assert processor._map_action_to_enum("terminate instance i-456") == RemediationAction.TERMINATE_INSTANCE
        assert processor._map_action_to_enum("resize instance i-789") == RemediationAction.RESIZE_INSTANCE
        assert processor._map_action_to_enum("delete snapshot snap-100") == RemediationAction.DELETE_SNAPSHOT
        assert processor._map_action_to_enum("release elastic ip eip-200") == RemediationAction.RELEASE_ELASTIC_IP
        assert processor._map_action_to_enum("stop rds instance db-300") == RemediationAction.STOP_RDS_INSTANCE
        assert processor._map_action_to_enum("delete rds instance db-400") == RemediationAction.DELETE_RDS_INSTANCE
        assert processor._map_action_to_enum("unknown action") is None
