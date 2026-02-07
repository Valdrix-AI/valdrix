import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.budget_manager import BudgetStatus
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture(autouse=True)
def reset_cache_singleton():
    """Reset the global cache service singleton before each test."""
    import app.shared.core.cache as cache_mod
    cache_mod._cache_service = None
    cache_mod._async_client = None
    # Patch get_settings globally to ensure enabled=True
    with patch("app.shared.core.cache.get_settings") as mock_settings:
        mock_settings.return_value.UPSTASH_REDIS_URL = "redis://test:6379"
        mock_settings.return_value.UPSTASH_REDIS_TOKEN = "test-token"
        yield

@pytest.fixture
def mock_llm():
    from langchain_core.language_models.chat_models import BaseChatModel
    llm = MagicMock(spec=BaseChatModel)
    llm.model_name = "gpt-4-test"
    llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"summary": "test"}'))
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
    # db = AsyncMock() # This line is removed as db is mocked inside the patch block
    
    with patch("app.shared.llm.analyzer.get_cache_service") as mock_cache_cls, \
         patch("app.shared.llm.analyzer.LLMBudgetManager") as MockBudget, \
         patch("app.shared.llm.usage_tracker.LLMBudgetManager") as MockBudgetTracker, \
         patch("app.shared.llm.analyzer.LLMGuardrails") as MockGuard, \
         patch("app.shared.llm.analyzer.SymbolicForecaster") as MockForecast, \
         patch("app.shared.llm.analyzer.LLMFactory") as MockFactory:
        
        # Ensure Factory returns our mock
        MockFactory.create.return_value = mock_llm
        
        # Configure cache mock BEFORE it's called
        mock_cache = AsyncMock()
        mock_cache.get_analysis = AsyncMock(return_value=None)
        mock_cache.set_analysis = AsyncMock()
        mock_cache_cls.return_value = mock_cache
        
        # Ensure BOTH mocks behave identically
        MockBudget.check_and_reserve = MockBudgetTracker.check_and_reserve = AsyncMock(return_value=Decimal("0.01"))
        MockBudget.record_usage = MockBudgetTracker.record_usage = AsyncMock()
        MockBudget.authorize_request = MockBudgetTracker.authorize_request = AsyncMock(return_value=Decimal("0.01"))
        MockBudget.check_budget = MockBudgetTracker.check_budget = AsyncMock(return_value=BudgetStatus.OK)
        
        # Database Mocking
        mock_budget_record = MagicMock()
        mock_budget_record.openai_api_key = "sk-test"
        mock_budget_record.monthly_limit_usd = Decimal("100.00")
        mock_budget_record.hard_limit = True
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget_record
        mock_result.scalar.return_value = Decimal("0")
        
        # Ensure db is an AsyncMock and its execute method is also an AsyncMock
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)
        # Ensure db can be used as an async context manager properly
        db.__aenter__.return_value = db
        
        # Analyzer uses llm and db
        analyzer = FinOpsAnalyzer(llm=mock_llm, db=db)
        # Ensure LLM is set
        analyzer.llm = mock_llm
        
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
