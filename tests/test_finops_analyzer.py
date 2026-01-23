
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json
from uuid import uuid4
from datetime import date, datetime
from decimal import Decimal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.services.llm.analyzer import FinOpsAnalyzer
from app.schemas.costs import CloudUsageSummary, CostRecord

# Mock system prompt for tests
FINOPS_SYSTEM_PROMPT = """
You are a FinOps expert. Analyze the cost data and return STRICT JSON ONLY.
"""

class TestFinOpsAnalyzerInstantiation:
    def test_requires_llm(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        assert analyzer.llm is mock_llm

@pytest.mark.asyncio
class TestAnalyze:
    async def test_invokes_llm_with_cost_data(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"insights":[],"zombie_resources":[],"recommendations":[],"summary":{"total_estimated_savings":"$0/month"}}'))
        
        from app.services.llm.budget_manager import LLMBudgetManager
        from app.services.analysis.forecaster import SymbolicForecaster
        
        mock_reserve = AsyncMock(return_value=Decimal("0.01"))
        mock_forecast = AsyncMock(return_value={"total_forecasted_cost": 0, "forecast": []})
        
        with AsyncMock() as mock_db:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
            
            tenant_id = str(uuid4())
            usage_summary = CloudUsageSummary(
                tenant_id=tenant_id,
                provider="aws",
                start_date=date.today(),
                end_date=date.today(),
                total_cost=Decimal("100.0"),
                records=[CostRecord(date=datetime.now(), amount=Decimal("100.0"), service="EC2")]
            )
            
            from app.services.llm.usage_tracker import BudgetStatus
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=mock_reserve):
                with patch.object(SymbolicForecaster, "forecast", side_effect=mock_forecast):
                    with patch("app.services.llm.usage_tracker.UsageTracker.check_budget", AsyncMock(return_value=BudgetStatus.OK)):
                        _ = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            
            mock_llm.ainvoke.assert_called_once()

    async def test_returns_parsed_result(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = {
            "insights": [],
            "zombie_resources": [],
            "recommendations": [],
            "summary": {"total_estimated_savings": "$0/month"}
        }
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(mock_response)))
        
        from app.services.llm.budget_manager import LLMBudgetManager
        from app.services.analysis.forecaster import SymbolicForecaster
        
        mock_reserve = AsyncMock(return_value=Decimal("0.05"))
        mock_forecast = AsyncMock(return_value={"total_forecasted_cost": 120, "forecast": []})

        with AsyncMock() as mock_db:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
            
            tenant_id = str(uuid4())
            usage_summary = CloudUsageSummary(
                tenant_id=tenant_id,
                provider="aws",
                start_date=date.today(),
                end_date=date.today(),
                total_cost=Decimal("100.0"),
                records=[CostRecord(date=datetime.now(), amount=Decimal("100.0"), service="EC2")]
            )
            
            from app.services.llm.usage_tracker import BudgetStatus
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=mock_reserve):
                with patch.object(SymbolicForecaster, "forecast", side_effect=mock_forecast):
                    with patch("app.services.llm.usage_tracker.UsageTracker.check_budget", AsyncMock(return_value=BudgetStatus.OK)):
                        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            
            assert "insights" in result
            assert result["symbolic_forecast"]["total_forecasted_cost"] == 120

    async def test_handles_markdown_wrapped_json(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = '```json\n{"insights":[],"zombie_resources":[],"recommendations":[],"summary":{"total_estimated_savings":"$0/month"}}\n```'
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=mock_response))
        
        from app.services.llm.budget_manager import LLMBudgetManager
        from app.services.analysis.forecaster import SymbolicForecaster
        
        mock_reserve = AsyncMock(return_value=Decimal("0.0"))
        mock_forecast = AsyncMock(return_value={"total_forecasted_cost": 0, "forecast": []})

        with AsyncMock() as mock_db:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
            
            tenant_id = str(uuid4())
            usage_summary = CloudUsageSummary(
                tenant_id=tenant_id,
                provider="aws",
                start_date=date.today(),
                end_date=date.today(),
                total_cost=Decimal("100.0"),
                records=[CostRecord(date=datetime.now(), amount=Decimal("100.0"), service="EC2")]
            )
            
            from app.services.llm.usage_tracker import BudgetStatus
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=mock_reserve):
                with patch.object(SymbolicForecaster, "forecast", side_effect=mock_forecast):
                    with patch("app.services.llm.usage_tracker.UsageTracker.check_budget", AsyncMock(return_value=BudgetStatus.OK)):
                        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            
            assert "insights" in result

    async def test_handles_invalid_json_gracefully(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="This is not valid JSON at all"))
        
        from app.services.llm.budget_manager import LLMBudgetManager
        from app.services.analysis.forecaster import SymbolicForecaster
        
        mock_reserve = AsyncMock(return_value=Decimal("0.0"))
        mock_forecast = AsyncMock(return_value={"total_forecasted_cost": 0, "forecast": []})

        with AsyncMock() as mock_db:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
            
            tenant_id = str(uuid4())
            usage_summary = CloudUsageSummary(
                tenant_id=tenant_id,
                provider="aws",
                start_date=date.today(),
                end_date=date.today(),
                total_cost=Decimal("100.0"),
                records=[CostRecord(date=datetime.now(), amount=Decimal("100.0"), service="EC2")]
            )
            
            from app.services.llm.usage_tracker import BudgetStatus
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=mock_reserve):
                with patch.object(SymbolicForecaster, "forecast", side_effect=mock_forecast):
                    with patch("app.services.llm.usage_tracker.UsageTracker.check_budget", AsyncMock(return_value=BudgetStatus.OK)):
                        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            assert result is not None

    async def test_handles_empty_cost_data(self):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"insights":[],"zombie_resources":[],"recommendations":[],"summary":{"total_estimated_savings":"$0/month"}}'))
        
        from app.services.llm.budget_manager import LLMBudgetManager
        from app.services.analysis.forecaster import SymbolicForecaster
        
        mock_reserve = AsyncMock(return_value=Decimal("0.0"))
        mock_forecast = AsyncMock(return_value={"total_forecasted_cost": 0, "forecast": []})

        with AsyncMock() as mock_db:
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
            
            tenant_id = str(uuid4())
            usage_summary = CloudUsageSummary(
                tenant_id=tenant_id,
                provider="aws",
                start_date=date.today(),
                end_date=date.today(),
                total_cost=Decimal("0.0"),
                records=[]
            )
            
            from app.services.llm.usage_tracker import BudgetStatus
            with patch.object(LLMBudgetManager, "check_and_reserve", side_effect=mock_reserve):
                with patch.object(SymbolicForecaster, "forecast", side_effect=mock_forecast):
                    with patch("app.services.llm.usage_tracker.UsageTracker.check_budget", AsyncMock(return_value=BudgetStatus.OK)):
                        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
            
            assert "recommendations" in result
