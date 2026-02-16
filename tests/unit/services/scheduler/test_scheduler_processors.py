import pytest
"""
Tests for Scheduler Processors - Analysis and Savings
No existing tests for these modules.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.modules.governance.domain.scheduler.processors import (
    AnalysisProcessor,
    SavingsProcessor,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_tenant():
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Tenant"
    return tenant


class TestAnalysisProcessor:
    """Tests for AnalysisProcessor."""

    def test_init(self) -> None:
        """Test processor initialization."""
        processor = AnalysisProcessor()
        assert processor.settings is not None

    @pytest.mark.asyncio
    async def test_process_tenant_success(self, mock_db: AsyncMock, mock_tenant) -> None:
        """Test processing tenant analysis."""
        processor = AnalysisProcessor()
        conn = MagicMock()
        conn.provider = "aws"
        conn.region = "us-east-1"
        mock_tenant.aws_connections = [conn]
        mock_tenant.azure_connections = []
        mock_tenant.gcp_connections = []
        mock_tenant.notification_settings = MagicMock(slack_enabled=False)
        # Mock dependencies
        with (
            patch(
                "app.modules.governance.domain.scheduler.processors.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory"
            ) as mock_detector_factory,
            patch(
                "app.modules.governance.domain.scheduler.processors.LLMFactory"
            ) as mock_llm_factory,
            patch(
                "app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer"
            ) as mock_analyzer,
        ):
            mock_adapter_instance = MagicMock()
            usage_summary = MagicMock()
            usage_summary.records = [MagicMock(amount=25.0, service="Amazon EC2")]
            usage_summary.total_cost = 25.0
            mock_adapter_instance.get_daily_costs = AsyncMock(
                return_value=usage_summary
            )
            mock_factory.get_adapter.return_value = mock_adapter_instance
            mock_detector_instance = mock_detector_factory.get_detector.return_value
            mock_detector_instance.scan_all = AsyncMock(return_value={"ec2": []})
            mock_llm = MagicMock()
            mock_llm_factory.create.return_value = mock_llm
            mock_analyzer.return_value.analyze = AsyncMock(
                return_value={"insights": [], "recommendations": []}
            )
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
        with patch(
            "app.modules.optimization.domain.remediation.RemediationService"
        ) as mock_service:
            mock_service_instance = MagicMock()
            mock_service_instance.create_request = AsyncMock(
                return_value=MagicMock(id=uuid4())
            )
            mock_service_instance.approve = AsyncMock()
            mock_service_instance.execute = AsyncMock()
            mock_service.return_value = mock_service_instance
            await processor.process_recommendations(mock_db, tenant_id, mock_result)
