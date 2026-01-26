
import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.usage_tracker import BudgetStatus
from app.schemas.costs import CloudUsageSummary
from datetime import date

@pytest.mark.asyncio
async def test_graceful_degradation_soft_limit():
    """Verify that analyzer switches to a cheaper model on SOFT_LIMIT."""
    # Mock dependencies
    mock_db = AsyncMock()
    mock_llm = AsyncMock()
    
    # Setup Analyzer
    analyzer = FinOpsAnalyzer(llm=mock_llm)
    
    # Mock UsageTracker and Budget
    tenant_id = uuid4()
    usage_tracker_mock = AsyncMock()
    usage_tracker_mock.check_budget.return_value = BudgetStatus.SOFT_LIMIT
    
    # Patch dependencies in analyzer
    from app.shared.llm.budget_manager import LLMBudgetManager
    from app.shared.analysis.forecaster import SymbolicForecaster

    with patch("app.shared.llm.analyzer.UsageTracker", return_value=usage_tracker_mock):
        with patch("app.shared.llm.analyzer.LLMFactory.create") as mock_factory:
            with patch.object(LLMBudgetManager, "check_and_reserve", AsyncMock(return_value=Decimal("0.01"))):
                with patch.object(SymbolicForecaster, "forecast", AsyncMock(return_value={"total_forecasted_cost": 0, "forecast": []})):
                    # Configure mocked DB budget lookup
                    mock_result = MagicMock()
                    mock_budget = MagicMock()
                    mock_budget.openai_api_key = "test_key"
                    mock_budget.preferred_provider = "openai"
                    mock_budget.preferred_model = "gpt-4"
                    mock_result.scalar_one_or_none.return_value = mock_budget
                    mock_db.execute.return_value = mock_result

                    # Configure mocked LLM
                    mock_degraded_llm = AsyncMock()
                    response_mock = MagicMock()
                    response_mock.content = '{"insights": [], "recommendations": [], "anomalies": [], "forecast": {}}'
                    response_mock.response_metadata = {}
                    mock_degraded_llm.ainvoke.return_value = response_mock
                    mock_factory.return_value = mock_degraded_llm
                    
                    summary = CloudUsageSummary(
                        tenant_id=str(tenant_id),
                        provider="aws",
                        start_date=date.today(),
                        end_date=date.today(),
                        total_cost=Decimal("0"),
                        records=[]
                    )
                    
                    # Analyze
                    await analyzer.analyze(
                        usage_summary=summary,
                        tenant_id=tenant_id,
                        db=mock_db,
                        provider="openai",
                        model="gpt-4"
                    )
            
            # Verify factory was called with cheaper model (gpt-4o-mini for openai)
            mock_factory.assert_called()
            args, kwargs = mock_factory.call_args
            assert args[0] == "openai" # provider
            assert kwargs["model"] == "gpt-4o-mini" # model should be downgraded
            
@pytest.mark.asyncio
async def test_hard_limit_blocking():
    """Verify that analyzer blocks requests on HARD_LIMIT."""
    mock_db = AsyncMock()
    mock_llm = AsyncMock()
    analyzer = FinOpsAnalyzer(llm=mock_llm)
    
    tenant_id = uuid4()
    usage_tracker_mock = AsyncMock()
    usage_tracker_mock.check_budget.return_value = BudgetStatus.HARD_LIMIT
    
    from app.shared.llm.budget_manager import LLMBudgetManager, BudgetExceededError
    with patch("app.shared.llm.analyzer.UsageTracker", return_value=usage_tracker_mock):
        summary = CloudUsageSummary(
            tenant_id=str(tenant_id),
            provider="aws",
            start_date=date.today(),
            end_date=date.today(),
            total_cost=Decimal("0"),
            records=[]
        )
        
        with pytest.raises(BudgetExceededError) as excinfo:
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=BudgetExceededError("Hard Limit reached")):
                await analyzer.analyze(summary, tenant_id=tenant_id, db=mock_db)
        
        assert "Hard Limit" in str(excinfo.value)
