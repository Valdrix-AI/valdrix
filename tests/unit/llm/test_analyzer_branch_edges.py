from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.core.constants import LLMProvider
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.budget_manager import BudgetStatus


def _build_usage_summary_with_record() -> CloudUsageSummary:
    now = datetime.now(timezone.utc)
    return CloudUsageSummary(
        tenant_id=str(uuid4()),
        provider="aws",
        start_date=date.today(),
        end_date=date.today(),
        total_cost=Decimal("1.0"),
        records=[
            CostRecord(
                date=now,
                amount=Decimal("1.0"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
            )
        ],
    )


def test_output_token_ceiling_and_bind_edge_cases() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    assert analyzer._resolve_output_token_ceiling(None) is None
    assert analyzer._resolve_output_token_ceiling("invalid") is None
    assert analyzer._resolve_output_token_ceiling(0) is None
    assert analyzer._resolve_output_token_ceiling(65536) == 32768

    assert analyzer._bind_output_token_ceiling(object(), 512) is None

    class _TypeThenErrorLLM:
        def __init__(self) -> None:
            self.calls = 0

        def bind(self, **_kwargs: object) -> object:
            self.calls += 1
            if self.calls == 1:
                raise TypeError("first signature mismatch")
            raise RuntimeError("unexpected bind failure")

    assert analyzer._bind_output_token_ceiling(_TypeThenErrorLLM(), 512) is None


@pytest.mark.asyncio
async def test_load_system_prompt_falls_back_when_system_prompt_blank() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    loop = SimpleNamespace(
        run_in_executor=AsyncMock(
            return_value={"finops_analysis": {"system": "   "}}
        )
    )

    with (
        patch("os.path.exists", return_value=True),
        patch("asyncio.get_running_loop", return_value=loop),
    ):
        prompt = await analyzer._load_system_prompt_async()

    assert "FinOps expert" in prompt


@pytest.mark.asyncio
async def test_check_cache_and_delta_parsing_fallback_branches() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    usage_summary = _build_usage_summary_with_record()
    recent_obj = SimpleNamespace(date=datetime.now(timezone.utc))
    bad_type_obj = SimpleNamespace(date=12345)
    cached = {"records": [{"date": "not-a-date"}, bad_type_obj, recent_obj]}
    cache = SimpleNamespace(get_analysis=AsyncMock(return_value=cached))

    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=cache),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.ENABLE_DELTA_ANALYSIS = True
        mock_settings.return_value.DELTA_ANALYSIS_DAYS = 7
        result, is_delta = await analyzer._check_cache_and_delta(
            uuid4(), False, usage_summary
        )

    assert is_delta is True
    assert result == cached
    assert hasattr(usage_summary, "_analysis_records_override")
    assert len(usage_summary._analysis_records_override) == 1


@pytest.mark.asyncio
async def test_analyze_handles_non_identical_records_without_override_attr() -> None:
    class _DynamicSummary:
        def __init__(self) -> None:
            self._records = [SimpleNamespace(date=datetime.now(timezone.utc))]
            self.tenant_id = str(uuid4())

        @property
        def records(self) -> list[SimpleNamespace]:
            # Return a fresh list each access so identity checks are false.
            return list(self._records)

        @records.setter
        def records(self, value: list[SimpleNamespace]) -> None:
            self._records = list(value)

        def model_dump(self) -> dict[str, object]:
            return {"records": []}

    analyzer = FinOpsAnalyzer(MagicMock())
    summary = _DynamicSummary()

    with (
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            analyzer,
            "_setup_client_and_usage",
            new=AsyncMock(return_value=("groq", "llama-3.3-70b-versatile", None)),
        ),
        patch.object(analyzer, "_invoke_llm", new=AsyncMock(return_value=("{}", {}))),
        patch.object(
            analyzer, "_process_analysis_results", new=AsyncMock(return_value={"ok": True})
        ),
    ):
        payload = await analyzer.analyze(summary)

    assert payload == {"ok": True}
    assert not hasattr(summary, "_analysis_records_override")


@pytest.mark.asyncio
async def test_setup_client_and_usage_provider_enum_and_soft_degradation() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
        mock_settings.return_value.LLM_PROVIDER = "groq"
        provider, model, byok = await analyzer._setup_client_and_usage(
            None, None, LLMProvider.OPENAI, None
        )

    assert provider == "openai"
    assert model == "gpt-4"
    assert byok is None

    budget = SimpleNamespace(
        openai_api_key=None,
        claude_api_key="sk-ant",
        google_api_key=None,
        groq_api_key=None,
        azure_api_key=None,
        preferred_provider=LLMProvider.ANTHROPIC,
        preferred_model="unknown-model",
    )
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: budget)
    tenant_id = uuid4()

    with (
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_budget",
            new=AsyncMock(return_value=BudgetStatus.SOFT_LIMIT),
        ),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        provider, model, byok = await analyzer._setup_client_and_usage(
            tenant_id, db, None, None
        )

    assert provider == "anthropic"
    assert model == "claude-3-5-haiku"
    assert byok == "sk-ant"


@pytest.mark.asyncio
async def test_setup_client_and_usage_keeps_safe_byok_custom_model() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    tenant_id = uuid4()
    db = AsyncMock()
    budget = SimpleNamespace(
        openai_api_key="sk-openai",
        claude_api_key=None,
        google_api_key=None,
        groq_api_key=None,
        azure_api_key=None,
        preferred_provider=LLMProvider.OPENAI,
        preferred_model="custom.model:v1/test",
    )
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: budget)

    with (
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_budget",
            new=AsyncMock(return_value=BudgetStatus.OK),
        ),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        provider, model, byok = await analyzer._setup_client_and_usage(
            tenant_id, db, None, None
        )

    assert provider == "openai"
    assert model == "custom.model:v1/test"
    assert byok == "sk-openai"


@pytest.mark.asyncio
async def test_invoke_llm_builds_factory_llm_when_bind_unavailable() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    class _Chain:
        async def ainvoke(self, _payload: dict[str, str]) -> object:
            return SimpleNamespace(content="{}", response_metadata={})

    class _Prompt:
        def __or__(self, _other: object) -> _Chain:
            return _Chain()

    with (
        patch.object(analyzer, "_get_prompt", new=AsyncMock(return_value=_Prompt())),
        patch.object(analyzer, "_bind_output_token_ceiling", return_value=None),
        patch("app.shared.llm.analyzer.LLMFactory.create", return_value=MagicMock()) as factory,
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        content, metadata = await analyzer._invoke_llm(
            formatted_data="{}",
            provider="groq",
            model="llama-3.3-70b-versatile",
            byok_key=None,
            max_output_tokens=256,
        )

    assert content == "{}"
    assert metadata == {}
    factory.assert_called_once_with(
        "groq",
        model="llama-3.3-70b-versatile",
        api_key=None,
        max_output_tokens=256,
    )


@pytest.mark.asyncio
async def test_process_results_unexpected_parse_and_non_dict_payload() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    usage_summary = MagicMock(records=[], tenant_id=None)

    cache = SimpleNamespace(set_analysis=AsyncMock())
    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=cache),
        patch(
            "app.shared.llm.analyzer.LLMGuardrails.validate_output",
            side_effect=Exception("validation-failed"),
        ),
        patch.object(analyzer, "_strip_markdown", side_effect=RuntimeError("parse-failed")),
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new=AsyncMock(return_value={}),
        ),
    ):
        parsed = await analyzer._process_analysis_results("###", None, usage_summary)

    assert parsed["llm_raw"]["error"] == "AI analysis processing failed"

    payload = SimpleNamespace(model_dump=lambda: ["not", "a", "dict"])
    with (
        patch("app.shared.llm.analyzer.get_cache_service", return_value=cache),
        patch("app.shared.llm.analyzer.LLMGuardrails.validate_output", return_value=payload),
        patch.object(analyzer, "_check_and_alert_anomalies", new=AsyncMock()),
        patch(
            "app.shared.llm.analyzer.SymbolicForecaster.forecast",
            new=AsyncMock(return_value={}),
        ),
    ):
        not_dict = await analyzer._process_analysis_results("{}", None, usage_summary)

    assert not_dict["llm_raw"]["error"] == "AI analysis produced non-object payload"


@pytest.mark.asyncio
async def test_check_and_alert_anomalies_missing_db_and_dispatch_failure() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    anomalies = [
        {
            "resource": "ec2-i-123",
            "issue": "cost spike",
            "cost_impact": "$25",
            "severity": "high",
        }
    ]

    with patch("app.shared.llm.analyzer.logger.warning") as warn:
        await analyzer._check_and_alert_anomalies(
            {"anomalies": anomalies}, tenant_id=uuid4(), db=None
        )
    warn.assert_called()

    slack = SimpleNamespace(send_alert=AsyncMock(side_effect=RuntimeError("slack-failed")))
    with patch("app.shared.llm.analyzer.get_slack_service", return_value=slack):
        await analyzer._check_and_alert_anomalies({"anomalies": anomalies})
