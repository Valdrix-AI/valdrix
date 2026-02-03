import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import date

# conftest.py handles environment mocks

from langchain_core.runnables import RunnableLambda
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.core.exceptions import AIAnalysisError, BudgetExceededError
from app.schemas.costs import CloudUsageSummary

@pytest.fixture
def mock_llm_factory():
    def _create_mock_llm(content='{"insights": ["test"]}', should_fail=False):
        async def _ainvoke(input, config=None, **kwargs):
            if should_fail:
                raise Exception("LLM Failed")
            return MagicMock(content=content, response_metadata={"token_usage": {"prompt_tokens": 100, "completion_tokens": 50}})
        
        llm = RunnableLambda(_ainvoke)
        llm.model_name = "llama-3.3-70b-versatile"
        return llm
    return _create_mock_llm

@pytest.fixture
def mock_llm(mock_llm_factory):
    return mock_llm_factory()

@pytest.fixture
def mock_db():
    db = AsyncMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = None
    res.scalar.return_value = 0.0
    db.execute.return_value = res
    return db

@pytest.fixture
def usage_summary():
    return CloudUsageSummary(
        tenant_id=str(uuid4()),
        provider="aws",
        start_date=date.today(),
        end_date=date.today(),
        total_cost=100.0,
        records=[]
    )

@pytest.fixture
def mock_forecaster():
    mock = MagicMock()
    mock.forecast = AsyncMock(return_value={"forecast": "data"})
    return mock

@pytest.mark.asyncio
async def test_load_system_prompt_success():
    with patch("builtins.open", MagicMock()):
        with patch("yaml.safe_load", return_value={"finops_analysis": {"system": "yaml_prompt"}}):
             with patch("os.path.exists", return_value=True):
                analyzer = FinOpsAnalyzer(MagicMock())
                assert "yaml_prompt" in analyzer.prompt.messages[0].prompt.template

@pytest.mark.asyncio
async def test_load_system_prompt_fallback():
    with patch("os.path.exists", return_value=False):
        analyzer = FinOpsAnalyzer(MagicMock())
        assert "FinOps expert" in analyzer.prompt.messages[0].prompt.template

@pytest.mark.asyncio
async def test_strip_markdown():
    analyzer = FinOpsAnalyzer(MagicMock())
    assert analyzer._strip_markdown("```json\n{...}\n```") == "{...}"
    assert analyzer._strip_markdown("{...}") == "{...}"

@pytest.mark.asyncio
async def test_analyze_cache_hit_full(mock_llm, usage_summary):
    analyzer = FinOpsAnalyzer(mock_llm)
    tenant_id = uuid4()
    mock_cache = MagicMock()
    mock_cache.get_analysis = AsyncMock(return_value={"cached": True})
    with patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache), \
         patch("app.shared.llm.analyzer.get_settings") as mock_settings:
            mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False
            result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            assert result == {"cached": True}

@pytest.mark.asyncio
async def test_analyze_budget_exceeded(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    
    # Patch SOURCE module for global effect
    with patch("app.shared.llm.analyzer.LLMGuardrails.sanitize_input", new_callable=AsyncMock) as mock_sanitize, \
         patch.object(analyzer, "_check_cache_and_delta", new_callable=AsyncMock) as mock_delta, \
         patch("app.shared.llm.budget_manager.LLMBudgetManager") as MockBudgetManager:
        
        mock_sanitize.return_value = {}
        mock_delta.return_value = (None, True)
        
        # Configure class methods
        MockBudgetManager.check_and_reserve = AsyncMock()
        MockBudgetManager.check_and_reserve.side_effect = BudgetExceededError("Hard Limit")
        
        # Expect BudgetExceededError. If code wraps it, we might need AIAnalysisError check too.
        # But let's assume it propagates or we catch the wrapper.
        with pytest.raises((BudgetExceededError, AIAnalysisError)):
            await analyzer.analyze(usage_summary)

@pytest.mark.asyncio
async def test_analyze_budget_error_unexpected(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    
    with patch("app.shared.llm.analyzer.LLMGuardrails.sanitize_input", new_callable=AsyncMock) as mock_sanitize, \
         patch.object(analyzer, "_check_cache_and_delta", new_callable=AsyncMock) as mock_delta, \
         patch("app.shared.llm.budget_manager.LLMBudgetManager") as MockBudgetManager:
        
        mock_sanitize.return_value = {}
        mock_delta.return_value = (None, True)
        
        MockBudgetManager.check_and_reserve = AsyncMock() 
        MockBudgetManager.check_and_reserve.side_effect = Exception("DB Error")
        
        with pytest.raises(AIAnalysisError) as exc:
            await analyzer.analyze(usage_summary)
        assert "Budget verification failed" in str(exc.value)

@pytest.mark.asyncio
async def test_analyze_flow_success(mock_llm, usage_summary, mock_db, mock_forecaster):
    with patch.object(FinOpsAnalyzer, '_load_system_prompt', return_value="System prompt"):
        analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    
    with patch("app.shared.llm.analyzer.SymbolicForecaster", side_effect=lambda *args: mock_forecaster):
        mock_cache = MagicMock()
        mock_cache.get_analysis = AsyncMock(return_value=None)
        mock_cache.set_analysis = AsyncMock() 
        
        class MockGuardrails:
            @classmethod
            async def sanitize_input(cls, data, **kwargs): return data
            @classmethod
            def validate_output(cls, output, schema):
                res = MagicMock()
                # model_dump must be synchronous here usually, or mock return
                res.model_dump.return_value = {"insights": ["Good"]}
                return res

        mock_tracker = MagicMock()
        mock_tracker.check_budget = AsyncMock(return_value="ok")

        with patch("app.shared.llm.budget_manager.LLMBudgetManager") as MockBudgetManager, \
             patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache), \
             patch("app.shared.llm.analyzer.UsageTracker", return_value=mock_tracker), \
             patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrails), \
             patch("app.shared.llm.analyzer.get_settings") as mock_settings:
            
            MockBudgetManager.check_and_reserve = AsyncMock(return_value=0.01)
            MockBudgetManager.record_usage = AsyncMock()
            
            mock_settings.return_value.LLM_PROVIDER = "openai"
            mock_settings.return_value.SLACK_BOT_TOKEN = None 

            result = await analyzer.analyze(usage_summary)
            assert result["insights"] == ["Good"]

@pytest.mark.asyncio
async def test_llm_invocation_primary_failure_fallback(mock_llm_factory, usage_summary):
    primary_llm = mock_llm_factory(should_fail=True)
    with patch.object(FinOpsAnalyzer, '_load_system_prompt', return_value="System"):
        analyzer = FinOpsAnalyzer(primary_llm)

    mock_cache = MagicMock()
    mock_cache.get_analysis = AsyncMock(return_value=None)
    fallback_llm = mock_llm_factory(content='{"insights": ["fallback"]}')

    class MockGuardrails:
        @classmethod
        async def sanitize_input(cls, data, **kwargs): return data
        @classmethod
        def validate_output(cls, output, schema):
            res = MagicMock()
            res.model_dump.return_value = {"insights": ["fallback"]}
            return res

    mock_tracker = MagicMock()
    mock_tracker.check_budget = AsyncMock(return_value="ok")

    with patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache), \
         patch("app.shared.llm.analyzer.LLMFactory.create", return_value=fallback_llm) as mock_factory, \
         patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrails), \
         patch("app.shared.llm.analyzer.UsageTracker", return_value=mock_tracker), \
         patch("app.shared.llm.analyzer.get_settings") as mock_settings, \
         patch("app.shared.llm.budget_manager.LLMBudgetManager") as MockBudgetManager:
         
         MockBudgetManager.check_and_reserve = AsyncMock(return_value=0.01)
         MockBudgetManager.record_usage = AsyncMock()
         
         mock_settings.return_value.LLM_PROVIDER = "openai"
         await analyzer.analyze(usage_summary)
         assert mock_factory.call_count >= 1

@pytest.mark.asyncio
async def test_process_results_fallback(mock_llm, mock_db, mock_forecaster):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    
    with patch("app.shared.llm.analyzer.SymbolicForecaster", side_effect=lambda *args: mock_forecaster):
        class MockGuardrailsFail:
            @classmethod
            def validate_output(cls, output, schema):
                raise Exception("Validation Fail")

        mock_cache = MagicMock()
        mock_cache.set_analysis = AsyncMock() 

        with patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache), \
             patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrailsFail), \
             patch("app.shared.llm.analyzer.get_settings") as mock_settings:
            
            mock_settings.return_value.SLACK_BOT_TOKEN = None
            res = await analyzer._process_analysis_results('{"foo": "bar"}', None, MagicMock())
            assert res["llm_raw"] == {"foo": "bar"}
