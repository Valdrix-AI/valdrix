import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model_name = "gpt-4-test"
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"insights": [], "recommendations": []}', response_metadata={"token_usage": {}}))
    return llm

@pytest.mark.asyncio
async def test_analyzer_budget_hard_limit(mock_llm):
    """Test that analyzer respects hard budget limits."""
    analyzer = FinOpsAnalyzer(mock_llm)
    
    usage_summary = MagicMock(records=[{"cost": 10}])
    usage_summary.model_dump.return_value = {"records": []}
    
    with patch("app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve", side_effect=BudgetExceededError("Limit Hit")):
        with pytest.raises(BudgetExceededError):
            await analyzer.analyze(
                usage_summary, 
                tenant_id=uuid4(), 
                db=AsyncMock()
            )

@pytest.mark.asyncio
async def test_analyzer_success_flow(mock_llm):
    """Test successful analysis flow."""
    analyzer = FinOpsAnalyzer(mock_llm)
    usage_summary = MagicMock(records=[{"cost": 10}])
    usage_summary.model_dump.return_value = {"records": []}
    
    tenant_id = uuid4()
    db = AsyncMock()
    
    with patch("app.shared.llm.analyzer.get_cache_service") as mock_cache_cls, \
         patch("app.shared.llm.analyzer.LLMBudgetManager") as MockBudget, \
         patch("app.shared.llm.analyzer.LLMGuardrails") as MockGuard, \
         patch("app.shared.llm.analyzer.SymbolicForecaster") as MockForecast:
        
        # Mocks
        mock_cache_cls.return_value.get_analysis = AsyncMock(return_value=None) # Cache miss
        MockBudget.check_and_reserve = AsyncMock(return_value=0.01)
        MockBudget.record_usage = AsyncMock()
        MockGuard.sanitize_input = AsyncMock(return_value={})
        
        # Explicitly force synchronous mock for validate_output
        mock_validated = MagicMock()
        mock_validated.model_dump.return_value = {
            "insights": ["Saved money"],
            "anomalies": []
        }
        MockGuard.validate_output = MagicMock(return_value=mock_validated)
        
        MockForecast.forecast = AsyncMock(return_value={})
        
        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id, db=db)
        
        assert "insights" in result
        MockBudget.check_and_reserve.assert_awaited()
        mock_llm.ainvoke.assert_awaited()
        MockBudget.record_usage.assert_awaited()
