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
    conn.region = "us-east-1"
    tenant.aws_connections = [conn]
    return tenant

@pytest.mark.asyncio
async def test_process_tenant_analysis(mock_db, mock_tenant):
    """Test full tenant analysis flow."""
    processor = AnalysisProcessor()
    
    # Mock dependencies
    with patch("app.modules.governance.domain.scheduler.processors.MultiTenantAWSAdapter") as MockAdapter, \
         patch("app.modules.governance.domain.scheduler.processors.LLMFactory"), \
         patch("app.modules.governance.domain.scheduler.processors.FinOpsAnalyzer") as MockAnalyzer, \
         patch("app.modules.governance.domain.scheduler.processors.ZombieDetector") as MockZombie, \
         patch("app.modules.governance.domain.scheduler.processors.CarbonCalculator"), \
         patch.dict("sys.modules", {"app.models.analysis": MagicMock(), "app.shared.llm.guardrails": MagicMock()}):
        
        # Mock CloudUsageSummary in the mocked module
        sys_modules = pytest.importorskip("sys").modules
        sys_modules["app.models.analysis"].CloudUsageSummary = MagicMock
        
        # Setup mocks
        adapter = MockAdapter.return_value
        adapter.get_daily_costs = AsyncMock(return_value=[{"cost": 100}])
        adapter.get_credentials = AsyncMock(return_value={})
        
        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock()
        
        zombie = MockZombie.return_value
        zombie.scan_all = AsyncMock(return_value={"ec2": []})
        
        # Run
        await processor.process_tenant(mock_db, mock_tenant, date.today(), date.today())
        
        # Verify calls
        adapter.get_daily_costs.assert_awaited()
        analyzer.analyze.assert_awaited()
        zombie.scan_all.assert_awaited()

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
