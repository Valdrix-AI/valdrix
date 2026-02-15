import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from langchain_core.runnables import RunnableLambda
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.core.constants import LLMProvider
from app.shared.core.exceptions import AIAnalysisError, BudgetExceededError
from app.schemas.costs import CloudUsageSummary, CostRecord


@pytest.fixture
def mock_llm_factory():
    def _create_mock_llm(content='{"insights": ["test"]}', should_fail=False):
        async def _ainvoke(input, config=None, **kwargs):
            if should_fail:
                raise Exception("LLM Failed")
            return MagicMock(
                content=content,
                response_metadata={
                    "token_usage": {"prompt_tokens": 100, "completion_tokens": 50}
                },
            )

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
    db.flush = AsyncMock()
    return db


@pytest.fixture
def usage_summary():
    return CloudUsageSummary(
        tenant_id=str(uuid4()),
        provider="aws",
        start_date=date.today(),
        end_date=date.today(),
        total_cost=Decimal("100.0"),
        records=[],
    )


@pytest.fixture
def usage_summary_with_records():
    now = datetime.now(timezone.utc)
    return CloudUsageSummary(
        tenant_id=str(uuid4()),
        provider="aws",
        start_date=now.date(),
        end_date=now.date(),
        total_cost=Decimal("100.0"),
        records=[
            CostRecord(
                date=now,
                amount=Decimal("10.0"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
            )
        ],
    )


@pytest.fixture
def mock_forecaster():
    mock = MagicMock()
    mock.forecast = AsyncMock(return_value={"forecast": "data"})
    return mock


@pytest.mark.asyncio
async def test_load_system_prompt_success():
    # Load the system prompt from yaml
    with patch("builtins.open", MagicMock()):
        with patch(
            "yaml.safe_load",
            return_value={"finops_analysis": {"system": "yaml_prompt"}},
        ):
            with patch("os.path.exists", return_value=True):
                analyzer = FinOpsAnalyzer(MagicMock())
                assert "yaml_prompt" in analyzer.prompt.messages[0].prompt.template


@pytest.mark.asyncio
async def test_load_system_prompt_fallback():
    # Fallback when file doesn't exist
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
    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False
        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id)
        assert result == {"cached": True}


@pytest.mark.asyncio
async def test_analyze_budget_exceeded(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)

    with (
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new_callable=AsyncMock,
        ) as mock_sanitize,
        patch.object(
            analyzer, "_check_cache_and_delta", new_callable=AsyncMock
        ) as mock_delta,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
    ):
        mock_sanitize.return_value = {}
        mock_delta.return_value = (None, True)
        mock_reserve.side_effect = BudgetExceededError("Hard Limit")

        with pytest.raises((BudgetExceededError, AIAnalysisError)):
            await analyzer.analyze(usage_summary, tenant_id=uuid4())


@pytest.mark.asyncio
async def test_analyze_budget_error_unexpected(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)

    with (
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new_callable=AsyncMock,
        ) as mock_sanitize,
        patch.object(
            analyzer, "_check_cache_and_delta", new_callable=AsyncMock
        ) as mock_delta,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
    ):
        mock_sanitize.return_value = {}
        mock_delta.return_value = (None, True)
        mock_reserve.side_effect = Exception("DB Error")

        with pytest.raises(AIAnalysisError) as exc:
            await analyzer.analyze(usage_summary, tenant_id=uuid4())
        assert "Budget verification failed" in str(exc.value)


@pytest.mark.asyncio
async def test_analyze_flow_success(mock_llm, usage_summary, mock_db, mock_forecaster):
    with patch.object(
        FinOpsAnalyzer, "_load_system_prompt", return_value="System prompt"
    ):
        analyzer = FinOpsAnalyzer(mock_llm, mock_db)

    mock_cache = MagicMock()
    mock_cache.get_analysis = AsyncMock(return_value=None)
    mock_cache.set_analysis = AsyncMock()

    class MockGuardrails:
        @classmethod
        async def sanitize_input(cls, data, **kwargs):
            return data

        @classmethod
        def validate_output(cls, output, schema):
            res = MagicMock()
            res.model_dump.return_value = {"insights": ["Good"]}
            return res

    mock_tracker = MagicMock()
    mock_tracker.check_budget = AsyncMock(return_value="ok")

    with (
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record,
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch("app.shared.llm.analyzer.UsageTracker", return_value=mock_tracker),
        patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrails),
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_reserve.return_value = Decimal("0.01")
        mock_record.return_value = None
        mock_forecast.return_value = {"forecast": "data"}

        mock_settings.return_value.LLM_PROVIDER = "openai"
        mock_settings.return_value.SLACK_BOT_TOKEN = None
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False

        result = await analyzer.analyze(usage_summary, tenant_id=uuid4(), db=mock_db)
        assert result["insights"] == ["Good"]


@pytest.mark.asyncio
async def test_llm_invocation_primary_failure_fallback(
    mock_llm_factory, usage_summary, mock_db
):
    primary_llm = mock_llm_factory(should_fail=True)
    with patch.object(FinOpsAnalyzer, "_load_system_prompt", return_value="System"):
        analyzer = FinOpsAnalyzer(primary_llm, mock_db)

    mock_cache = MagicMock()
    mock_cache.get_analysis = AsyncMock(return_value=None)
    mock_cache.set_analysis = AsyncMock()
    fallback_llm = mock_llm_factory(content='{"insights": ["fallback"]}')

    class MockGuardrails:
        @classmethod
        async def sanitize_input(cls, data, **kwargs):
            return data

        @classmethod
        def validate_output(cls, output, schema):
            res = MagicMock()
            res.model_dump.return_value = {"insights": ["fallback"]}
            return res

    mock_tracker = MagicMock()
    mock_tracker.check_budget = AsyncMock(return_value="ok")

    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch(
            "app.shared.llm.analyzer.LLMFactory.create", return_value=fallback_llm
        ) as mock_factory,
        patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrails),
        patch("app.shared.llm.analyzer.UsageTracker", return_value=mock_tracker),
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ),
    ):
        mock_reserve.return_value = Decimal("0.01")
        mock_forecast.return_value = {"forecast": "data"}

        mock_settings.return_value.LLM_PROVIDER = "openai"
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False
        await analyzer.analyze(usage_summary, tenant_id=uuid4(), db=mock_db)
        assert mock_factory.call_count >= 1
        assert any(
            call.args[0] == LLMProvider.GROQ
            and call.kwargs.get("model") == "llama-3.3-70b-versatile"
            for call in mock_factory.call_args_list
        )


@pytest.mark.asyncio
async def test_process_results_fallback(mock_llm, mock_db, mock_forecaster):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)

    with patch(
        "app.shared.llm.analyzer.SymbolicForecaster.forecast", new_callable=AsyncMock
    ) as mock_forecast:
        mock_forecast.return_value = {"forecast": "data"}

        class MockGuardrailsFail:
            @classmethod
            def validate_output(cls, output, schema):
                raise Exception("Validation Fail")

        mock_cache = MagicMock()
        mock_cache.set_analysis = AsyncMock()

        with (
            patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
            patch("app.shared.llm.analyzer.LLMGuardrails", new=MockGuardrailsFail),
            patch("app.shared.llm.analyzer.get_settings") as mock_settings,
        ):
            mock_settings.return_value.SLACK_BOT_TOKEN = None
            res = await analyzer._process_analysis_results(
                '{"foo": "bar"}', None, MagicMock(records=[], tenant_id=None)
            )
            assert res["llm_raw"] == {"foo": "bar"}


@pytest.mark.asyncio
async def test_analyze_force_refresh(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    tenant_id = uuid4()
    mock_cache = MagicMock()
    mock_cache.get_analysis = AsyncMock(return_value={"cached": True})

    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new_callable=AsyncMock,
        ) as mock_sanitize,
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
        patch.object(
            analyzer,
            "_setup_client_and_usage",
            return_value=(None, "groq", "llama-3.3-70b-versatile", None),
        ),
        patch.object(analyzer, "_invoke_llm", new_callable=AsyncMock) as mock_invoke,
        patch.object(
            analyzer, "_process_analysis_results", new_callable=AsyncMock
        ) as mock_proc,
    ):
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False
        mock_reserve.return_value = Decimal("0.01")
        mock_sanitize.return_value = {}
        mock_forecast.return_value = {}
        mock_invoke.return_value = ('{"fresh": True}', {"metadata": "test"})
        mock_proc.return_value = {"fresh": True}

        # Should skip cache because force_refresh=True
        result = await analyzer.analyze(
            usage_summary, tenant_id=tenant_id, force_refresh=True, db=mock_db
        )
        assert result == {"fresh": True}
        assert mock_invoke.called


@pytest.mark.asyncio
async def test_analyze_with_delta_analysis_enabled(
    mock_llm, usage_summary_with_records, mock_db
):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    tenant_id = uuid4()

    mock_cache = MagicMock()
    # Initial cached content needs records for delta cutoff logic
    mock_cache.get_analysis = AsyncMock(
        return_value={
            "cached": True,
            "records": [r.model_dump() for r in usage_summary_with_records.records],
        }
    )

    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new_callable=AsyncMock,
        ) as mock_sanitize,
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
        patch.object(
            analyzer,
            "_setup_client_and_usage",
            return_value=(None, "groq", "llama-3.3-70b-versatile", None),
        ),
        patch.object(analyzer, "_invoke_llm", new_callable=AsyncMock) as mock_invoke,
        patch.object(
            analyzer, "_process_analysis_results", new_callable=AsyncMock
        ) as mock_proc,
    ):
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = True
        mock_settings.return_value.DELTA_ANALYSIS_DAYS = 7
        mock_reserve.return_value = Decimal("0.01")
        mock_sanitize.return_value = {}
        mock_forecast.return_value = {}
        mock_invoke.return_value = ('{"fresh": True}', {"metadata": "test"})
        mock_proc.return_value = {"fresh": True}

        result = await analyzer.analyze(
            usage_summary_with_records, tenant_id=tenant_id, db=mock_db
        )
        assert result == {"fresh": True}
        assert mock_invoke.called


@pytest.mark.asyncio
async def test_invoke_llm_failure_retry(mock_llm_factory, usage_summary, mock_db):
    # Test case where LLM fails and retry is triggered
    failing_llm = mock_llm_factory(should_fail=True)
    analyzer = FinOpsAnalyzer(failing_llm, mock_db)

    # Speed up retry for testing
    from tenacity import stop_after_attempt, wait_none

    with (
        patch(
            "app.shared.llm.analyzer.stop_after_attempt",
            return_value=stop_after_attempt(1),
        ),
        patch("app.shared.llm.analyzer.wait_exponential", return_value=wait_none()),
    ):
        with pytest.raises(Exception):
            await analyzer._invoke_llm("data", "openai", "model", None)


@pytest.mark.asyncio
async def test_process_results_with_slack_alert(mock_llm, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)

    with (
        patch("app.shared.llm.analyzer.get_slack_service") as mock_get_slack,
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
    ):
        mock_slack = MagicMock()
        mock_slack.send_alert = AsyncMock()
        mock_get_slack.return_value = mock_slack
        mock_forecast.return_value = {}

        # Content with anomaly to trigger alert
        content = json.dumps(
            {
                "insights": [],
                "recommendations": [],
                "anomalies": [
                    {
                        "resource": "ec2",
                        "issue": "spike",
                        "cost_impact": "$10",
                        "severity": "high",
                    }
                ],
                "forecast": {},
            }
        )

        await analyzer._process_analysis_results(
            content, None, MagicMock(records=[], tenant_id=uuid4())
        )
        mock_slack.send_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_cache_and_delta_no_tenant(mock_llm):
    analyzer = FinOpsAnalyzer(mock_llm)
    res, is_delta = await analyzer._check_cache_and_delta(None, False, MagicMock())
    assert res is None
    assert not is_delta


@pytest.mark.asyncio
async def test_check_cache_and_delta_no_new_data(mock_llm, usage_summary):
    analyzer = FinOpsAnalyzer(mock_llm)
    mock_cache = MagicMock()
    # Records are from 30 days ago, delta cutoff is 7 days
    old_dt = datetime.now(timezone.utc) - timedelta(days=30)
    mock_cache.get_analysis = AsyncMock(return_value={"records": [{"date": old_dt}]})

    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=mock_cache),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = True
        mock_settings.return_value.DELTA_ANALYSIS_DAYS = 7
        res, is_delta = await analyzer._check_cache_and_delta(
            uuid4(), False, usage_summary
        )
        assert not is_delta


@pytest.mark.asyncio
async def test_analyze_data_prep_failure(mock_llm, usage_summary, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    with (
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            side_effect=Exception("Sanitize fail"),
        ),
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
    ):
        mock_reserve.return_value = Decimal("0.01")
        with pytest.raises(AIAnalysisError) as exc:
            await analyzer.analyze(usage_summary, tenant_id=uuid4(), db=mock_db)
        assert "prepare data" in str(exc.value)


@pytest.mark.asyncio
async def test_analyze_usage_recording_failure(
    mock_llm, usage_summary_with_records, mock_db
):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    with (
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record,
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new_callable=AsyncMock,
        ) as mock_sanitize,
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new_callable=AsyncMock,
        ) as mock_forecast,
        patch.object(
            analyzer,
            "_setup_client_and_usage",
            return_value=(None, "groq", "llama-3.3-70b-versatile", None),
        ),
        patch.object(analyzer, "_invoke_llm", return_value=("{}", {})),
        patch.object(analyzer, "_process_analysis_results", return_value={}),
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
    ):
        mock_reserve.return_value = Decimal("0.01")
        mock_record.side_effect = Exception("Record fail")
        mock_sanitize.return_value = {}
        mock_forecast.return_value = {}
        # Should NOT raise error, just log warning
        await analyzer.analyze(
            usage_summary_with_records, tenant_id=uuid4(), db=mock_db
        )


@pytest.mark.asyncio
async def test_process_results_json_failure(mock_llm, mock_db):
    analyzer = FinOpsAnalyzer(mock_llm, mock_db)
    with patch("app.shared.llm.analyzer.SymbolicForecaster.forecast", return_value={}):
        res = await analyzer._process_analysis_results(
            "Invalid JSON", None, MagicMock(records=[], tenant_id=None)
        )
        assert res["llm_raw"]["error"] == "AI analysis format invalid"
