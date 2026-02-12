import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date
from uuid import uuid4
from app.modules.governance.domain.scheduler.processors import AnalysisProcessor, SavingsProcessor

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_tenant():
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.name = "Test Tenant"
    tenant.notification_settings = MagicMock(slack_enabled=False)
    # Mock AWS connections
    conn = MagicMock()
    conn.id = uuid4()
    conn.provider = "aws"
    conn.region = "us-east-1"
    tenant.aws_connections = [conn]
    tenant.azure_connections = []
    tenant.gcp_connections = []
    return tenant

@pytest.mark.asyncio
async def test_process_tenant_analysis(mock_db, mock_tenant):
    """Test full tenant analysis flow."""
    processor = AnalysisProcessor()
    
    # Mock dependencies
    with patch("app.modules.governance.domain.scheduler.processors.AdapterFactory") as mock_factory, \
         patch("app.modules.governance.domain.scheduler.processors.LLMFactory"), \
         patch("app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer") as MockAnalyzer, \
         patch("app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory") as mock_detector_factory, \
         patch("app.modules.governance.domain.scheduler.processors.CarbonCalculator"):
        # Setup mocks
        adapter = MagicMock()
        usage_summary = MagicMock()
        usage_summary.records = [MagicMock(amount=100.0, service="Amazon EC2")]
        usage_summary.total_cost = 100.0
        adapter.get_daily_costs = AsyncMock(return_value=usage_summary)
        mock_factory.get_adapter.return_value = adapter
        
        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock(return_value={"insights": [], "recommendations": []})
        
        zombie = mock_detector_factory.get_detector.return_value
        zombie.scan_all = AsyncMock(return_value={"ec2": []})
        
        # Run
        await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())
        
        # Verify calls
        adapter.get_daily_costs.assert_awaited()
        analyzer.analyze.assert_awaited()
        zombie.scan_all.assert_awaited()


@pytest.mark.asyncio
async def test_process_tenant_analysis_azure_path_uses_global_detector(mock_db, mock_tenant):
    processor = AnalysisProcessor()
    azure_conn = MagicMock()
    azure_conn.id = uuid4()
    azure_conn.provider = "azure"
    mock_tenant.aws_connections = []
    mock_tenant.azure_connections = [azure_conn]
    mock_tenant.gcp_connections = []

    with patch("app.modules.governance.domain.scheduler.processors.AdapterFactory") as mock_factory, \
         patch("app.modules.governance.domain.scheduler.processors.LLMFactory"), \
         patch("app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer") as MockAnalyzer, \
         patch("app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory") as mock_detector_factory, \
         patch("app.modules.governance.domain.scheduler.processors.CarbonCalculator"):
        adapter = MagicMock()
        adapter.get_cost_and_usage = AsyncMock(
            return_value=[
                {
                    "timestamp": "2026-02-01T00:00:00+00:00",
                    "service": "Virtual Machines",
                    "cost_usd": 12.5,
                    "provider": "azure",
                }
            ]
        )
        mock_factory.get_adapter.return_value = adapter

        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock(return_value={"insights": [], "recommendations": []})

        detector = mock_detector_factory.get_detector.return_value
        detector.scan_all = AsyncMock(return_value={"idle_azure_vms": []})

        await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())

        mock_detector_factory.get_detector.assert_called_once()
        detector.scan_all.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_tenant_saas_path_runs_zombie_detection(mock_db, mock_tenant):
    processor = AnalysisProcessor()
    saas_conn = MagicMock()
    saas_conn.id = uuid4()
    saas_conn.provider = "saas"
    mock_tenant.aws_connections = []
    mock_tenant.azure_connections = []
    mock_tenant.gcp_connections = []
    mock_tenant.saas_connections = [saas_conn]
    mock_tenant.license_connections = []

    with patch("app.modules.governance.domain.scheduler.processors.AdapterFactory") as mock_factory, \
         patch("app.modules.governance.domain.scheduler.processors.LLMFactory"), \
         patch("app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer") as MockAnalyzer, \
         patch("app.modules.governance.domain.scheduler.processors.ZombieDetectorFactory") as mock_detector_factory, \
         patch("app.modules.governance.domain.scheduler.processors.CarbonCalculator"):
        adapter = MagicMock()
        adapter.get_cost_and_usage = AsyncMock(
            return_value=[
                {
                    "timestamp": "2026-02-01T00:00:00+00:00",
                    "service": "Slack",
                    "cost_usd": 25.0,
                    "provider": "saas",
                }
            ]
        )
        mock_factory.get_adapter.return_value = adapter

        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock(return_value={"insights": [], "recommendations": []})

        detector = mock_detector_factory.get_detector.return_value
        detector.scan_all = AsyncMock(return_value={"idle_saas_subscriptions": []})

        await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())

        mock_detector_factory.get_detector.assert_called_once()
        detector.scan_all.assert_awaited_once()

@pytest.mark.asyncio
async def test_savings_autopilot_execution(mock_db):
    """Test autonomous savings execution."""
    processor = SavingsProcessor()
    tenant_id = uuid4()
    
    # Mock Analysis Result with recommendation
    rec = MagicMock()
    rec.autonomous_ready = True
    rec.confidence = "high"
    rec.action = "Stop Instance"
    rec.resource = "i-123"
    rec.resource_type = "ec2"
    rec.estimated_savings = "$10/month"
    
    analysis_result = MagicMock()
    analysis_result.recommendations = [rec]
    
    with patch("app.modules.optimization.domain.remediation.RemediationService") as MockRemediation:
        service = MockRemediation.return_value
        service.create_request = AsyncMock(return_value=MagicMock(id=uuid4()))
        service.approve = AsyncMock()
        service.execute = AsyncMock()
        
        await processor.process_recommendations(mock_db, tenant_id, analysis_result)
        
        service.create_request.assert_awaited()
        service.approve.assert_awaited()
        service.execute.assert_awaited()
