import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json
from uuid import uuid4
from datetime import date, datetime
from decimal import Decimal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.shared.llm.analyzer import FinOpsAnalyzer
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
    @pytest.fixture
    def mock_usage_summary(self):
        tenant_id = str(uuid4())
        return CloudUsageSummary(
            tenant_id=tenant_id,
            provider="aws",
            start_date=date.today(),
            end_date=date.today(),
            total_cost=Decimal("100.0"),
            records=[
                CostRecord(date=datetime.now(), amount=Decimal("100.0"), service="EC2")
            ],
        )

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        res = MagicMock()
        res.scalar_one_or_none.return_value = None
        db.execute.return_value = res
        return db

    async def test_invokes_llm_with_cost_data(self, mock_usage_summary, mock_db):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"summary":"ok","anomalies":[],"recommendations":[],"estimated_total_savings":0}'
            )
        )

        analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)

        patch_paths = [
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            "app.shared.llm.analyzer.get_cache_service",
            "app.shared.llm.analyzer.SlackService",
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            "app.shared.llm.analyzer.LLMGuardrails.validate_output",
            "app.shared.llm.analyzer.UsageTracker.check_budget",
        ]

        with (
            patch(patch_paths[0], new_callable=AsyncMock) as m_reserve,
            patch(patch_paths[1], new_callable=AsyncMock),
            patch(patch_paths[2], new_callable=AsyncMock) as m_forecast,
            patch(patch_paths[3]) as m_cache_svc,
            patch(patch_paths[4]),
            patch(patch_paths[5], new_callable=AsyncMock) as m_sanitize,
            patch(patch_paths[6]) as m_validate,
            patch(patch_paths[7], new_callable=AsyncMock) as m_budget,
        ):
            m_reserve.return_value = Decimal("0.01")
            m_forecast.return_value = {"total_forecasted_cost": 0, "forecast": []}
            m_cache_svc.return_value.get_analysis = AsyncMock(return_value=None)
            m_cache_svc.return_value.set_analysis = AsyncMock()
            m_cache_svc.return_value.enabled = False
            m_sanitize.return_value = {"records": []}

            # Setup validation mock to return a model with model_dump
            mock_validated = MagicMock()
            mock_validated.model_dump.return_value = {"anomalies": [], "summary": "ok"}
            m_validate.return_value = mock_validated

            from app.shared.llm.usage_tracker import BudgetStatus

            m_budget.return_value = BudgetStatus.OK

            _ = await analyzer.analyze(
                mock_usage_summary, tenant_id=mock_usage_summary.tenant_id
            )

            mock_llm.ainvoke.assert_called_once()

    async def test_returns_parsed_result(self, mock_usage_summary, mock_db):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = {
            "insights": [],
            "anomalies": [],
            "recommendations": [],
            "forecast": {},
            "summary": "ok",
        }
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content=json.dumps(mock_response))
        )

        analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)

        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                AsyncMock(return_value=Decimal("0.05")),
            ),
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage", AsyncMock()),
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast",
                AsyncMock(return_value={"total_forecasted_cost": 120}),
            ),
            patch("app.shared.llm.analyzer.get_cache_service") as m_cache,
        ):
            m_cache.return_value.get_analysis = AsyncMock(return_value=None)
            m_cache.return_value.set_analysis = AsyncMock()

            result = await analyzer.analyze(
                mock_usage_summary, tenant_id=mock_usage_summary.tenant_id
            )

            assert "insights" in result
            assert result["symbolic_forecast"]["total_forecasted_cost"] == 120

    async def test_handles_markdown_wrapped_json(self, mock_usage_summary, mock_db):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = '```json\n{"insights":[],"anomalies":[],"recommendations":[],"summary":"ok"}\n```'
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=mock_response))

        analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)

        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                AsyncMock(return_value=Decimal("0")),
            ),
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage", AsyncMock()),
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast",
                AsyncMock(return_value={}),
            ),
            patch("app.shared.llm.analyzer.get_cache_service") as m_cache,
        ):
            m_cache.return_value.get_analysis = AsyncMock(return_value=None)
            m_cache.return_value.set_analysis = AsyncMock()

            result = await analyzer.analyze(
                mock_usage_summary, tenant_id=mock_usage_summary.tenant_id
            )
            assert "insights" in result

    async def test_handles_invalid_json_gracefully(self, mock_usage_summary, mock_db):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(content="This is not valid JSON at all")
        )

        analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)

        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                AsyncMock(return_value=Decimal("0")),
            ),
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage", AsyncMock()),
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast",
                AsyncMock(return_value={}),
            ),
            patch("app.shared.llm.analyzer.get_cache_service") as m_cache,
        ):
            m_cache.return_value.get_analysis = AsyncMock(return_value=None)
            m_cache.return_value.set_analysis = AsyncMock()

            result = await analyzer.analyze(
                mock_usage_summary, tenant_id=mock_usage_summary.tenant_id
            )
            assert result is not None
            assert "llm_raw" in result

    async def test_handles_empty_cost_data(self, mock_usage_summary, mock_db):
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(
            return_value=AIMessage(
                content='{"insights":[],"anomalies":[],"recommendations":[],"summary":"ok"}'
            )
        )

        analyzer = FinOpsAnalyzer(llm=mock_llm, db=mock_db)
        mock_usage_summary.records = []

        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                AsyncMock(return_value=Decimal("0")),
            ),
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage", AsyncMock()),
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast",
                AsyncMock(return_value={}),
            ),
            patch("app.shared.llm.analyzer.get_cache_service") as m_cache,
        ):
            m_cache.return_value.get_analysis = AsyncMock(return_value=None)
            m_cache.return_value.set_analysis = AsyncMock()

            result = await analyzer.analyze(
                mock_usage_summary, tenant_id=mock_usage_summary.tenant_id
            )
            assert "recommendations" in result
