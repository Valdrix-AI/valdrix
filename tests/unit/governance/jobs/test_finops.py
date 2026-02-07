import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.finops import FinOpsAnalysisHandler

@pytest.mark.asyncio
async def test_finops_analysis_handler():
    """Test FinOps analysis background job."""
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = AsyncMock()
    
    # Mock AWS connection query
    db.execute.return_value.scalar_one_or_none.return_value = MagicMock(id=uuid4())
    
    with patch("app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter") as MockAdapter, \
         patch("app.shared.llm.factory.LLMFactory.create"), \
         patch("app.shared.llm.analyzer.FinOpsAnalyzer") as MockAnalyzer:
        
        adapter = MockAdapter.return_value
        adapter.get_daily_costs = AsyncMock(return_value=[])
        
        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock(return_value={"result": "ok"})
        
        res = await handler.execute(job, db)
        
        assert res["status"] == "completed"
        analyzer.analyze.assert_awaited()
