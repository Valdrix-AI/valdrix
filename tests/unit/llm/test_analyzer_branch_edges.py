from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.core.constants import LLMProvider
from app.shared.core.exceptions import BudgetExceededError
from app.shared.core.pricing import PricingTier
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

    class _AllTypeErrorsLLM:
        def bind(self, **_kwargs: object) -> object:
            raise TypeError("unsupported kwarg")

    assert analyzer._bind_output_token_ceiling(_AllTypeErrorsLLM(), 512) is None


def test_resolve_positive_limit_and_record_to_date_edge_cases() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    assert analyzer._resolve_positive_limit(None) is None
    assert analyzer._resolve_positive_limit("not-an-int") is None
    assert analyzer._resolve_positive_limit(0, minimum=1) is None
    assert analyzer._resolve_positive_limit(5_000_000, maximum=99) == 99

    today = date.today()
    now = datetime.now(timezone.utc)
    assert analyzer._record_to_date({"date": today}) == today
    assert analyzer._record_to_date({"date": now.isoformat()}) == now.date()
    assert analyzer._record_to_date(SimpleNamespace(date=now)) == now.date()
    assert analyzer._record_to_date(SimpleNamespace(date="bad-date")) is None
    assert analyzer._record_to_date(SimpleNamespace(date=1234)) is None


def test_apply_tier_analysis_shape_limits_no_limits_returns_original_summary() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    usage_summary = SimpleNamespace(
        records=[SimpleNamespace(date=datetime(2026, 1, 1, tzinfo=timezone.utc))]
    )

    with patch("app.shared.llm.analyzer.get_tier_limit", return_value=None):
        summary_out, limits = analyzer._apply_tier_analysis_shape_limits(
            usage_summary,
            tenant_tier=PricingTier.GROWTH,
        )

    assert summary_out is usage_summary
    assert limits["records_before"] == 1
    assert limits["records_after"] == 1


def test_apply_tier_analysis_shape_limits_window_and_record_caps_trim_deterministically() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    records = [
        {"date": "2026-01-01T00:00:00+00:00", "service": "s1"},
        {"date": "2026-01-02T00:00:00+00:00", "service": "s2"},
        {"date": "2026-01-03T00:00:00+00:00", "service": "s3"},
        {"date": "2026-01-04T00:00:00+00:00", "service": "s4"},
        {"date": "2026-01-05T00:00:00+00:00", "service": "s5"},
        {"date": "2026-01-06T00:00:00+00:00", "service": "s6"},
        {"date": "2026-01-07T00:00:00+00:00", "service": "s7"},
    ]
    usage_summary = SimpleNamespace(records=records)

    tier_limits = {
        "llm_analysis_max_window_days": 4,
        "llm_prompt_max_input_tokens": 256,  # prompt-derived cap = 12
        "llm_analysis_max_records": 3,
    }

    with patch(
        "app.shared.llm.analyzer.get_tier_limit",
        side_effect=lambda _tier, key: tier_limits.get(key),
    ):
        summary_out, limits = analyzer._apply_tier_analysis_shape_limits(
            usage_summary,
            tenant_tier=PricingTier.GROWTH,
        )

    assert summary_out is not usage_summary
    assert limits["max_window_days"] == 4
    assert limits["max_prompt_tokens"] == 256
    assert limits["max_records"] == 3
    assert limits["records_before"] == 7
    assert limits["records_after"] == 3
    kept_dates = [item["date"][:10] for item in summary_out.records]
    assert kept_dates == ["2026-01-05", "2026-01-06", "2026-01-07"]


@pytest.mark.asyncio
async def test_get_prompt_returns_cached_prompt_without_reloading() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    analyzer.prompt = object()  # type: ignore[assignment]

    with patch.object(analyzer, "_load_system_prompt_async", new=AsyncMock()) as loader:
        prompt = await analyzer._get_prompt()

    assert prompt is analyzer.prompt
    loader.assert_not_awaited()


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
async def test_load_system_prompt_falls_back_when_executor_raises() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    loop = SimpleNamespace(run_in_executor=AsyncMock(side_effect=RuntimeError("boom")))

    with (
        patch("os.path.exists", return_value=True),
        patch("asyncio.get_running_loop", return_value=loop),
    ):
        prompt = await analyzer._load_system_prompt_async()

    assert "FinOps expert" in prompt


@pytest.mark.asyncio
async def test_load_system_prompt_falls_back_when_registry_missing_finops_key() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    loop = SimpleNamespace(run_in_executor=AsyncMock(return_value={"other_prompt": {}}))

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
    date_dict_record = {
        "date": date.today(),
        "amount": Decimal("2.5"),
        "service": "AmazonS3",
        "region": "us-east-1",
        "usage_type": "TimedStorage-ByteHrs",
    }
    cached = {"records": [{"date": "not-a-date"}, bad_type_obj, recent_obj, date_dict_record]}
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
    assert len(usage_summary._analysis_records_override) == 2
    assert any(
        getattr(record, "service", None) == "AmazonS3"
        for record in usage_summary._analysis_records_override
    )


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
@pytest.mark.parametrize(
    ("preferred_provider", "preferred_model", "expected_model"),
    [
        (LLMProvider.GROQ, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        (LLMProvider.OPENAI, "gpt-4o", "gpt-4o-mini"),
        (LLMProvider.GOOGLE, "gemini-1.5-pro", "gemini-1.5-flash"),
    ],
)
async def test_setup_client_and_usage_soft_limit_degrades_provider_specific_models(
    preferred_provider: LLMProvider,
    preferred_model: str,
    expected_model: str,
) -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    tenant_id = uuid4()
    db = AsyncMock()
    budget = SimpleNamespace(
        openai_api_key=None,
        claude_api_key=None,
        google_api_key=None,
        groq_api_key=None,
        azure_api_key=None,
        preferred_provider=preferred_provider,
        preferred_model=preferred_model,
    )
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: budget)

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

    assert provider == preferred_provider.value
    assert model == expected_model
    assert byok is None


@pytest.mark.asyncio
async def test_setup_client_and_usage_soft_limit_keeps_azure_model_when_no_degradation_mapping() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    tenant_id = uuid4()
    db = AsyncMock()
    budget = SimpleNamespace(
        openai_api_key=None,
        claude_api_key=None,
        google_api_key=None,
        groq_api_key=None,
        azure_api_key="azure-key",
        preferred_provider=LLMProvider.AZURE,
        preferred_model="gpt-4",
    )
    db.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: budget)

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

    assert provider == "azure"
    assert model == "gpt-4"
    assert byok == "azure-key"


@pytest.mark.asyncio
async def test_setup_client_and_usage_hard_limit_raises_budget_exceeded() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    with patch(
        "app.shared.llm.analyzer.LLMBudgetManager.check_budget",
        new=AsyncMock(return_value=BudgetStatus.HARD_LIMIT),
    ):
        with pytest.raises(BudgetExceededError, match="Monthly LLM budget exceeded"):
            await analyzer._setup_client_and_usage(uuid4(), AsyncMock(), None, None)


@pytest.mark.asyncio
async def test_setup_client_and_usage_invalid_provider_falls_back_to_default() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
        mock_settings.return_value.LLM_PROVIDER = "groq"
        provider, model, byok = await analyzer._setup_client_and_usage(
            None, None, "not-a-real-provider", "made-up-model"
        )

    assert provider == "groq"
    assert model == "llama-3.3-70b-versatile"
    assert byok is None


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
async def test_invoke_llm_uses_factory_for_non_default_provider_with_byok_and_ceiling() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    class _LLM:
        pass

    class _Chain:
        async def ainvoke(self, _payload: dict[str, str]) -> object:
            return SimpleNamespace(
                content={"ok": True},
                response_metadata="not-a-dict",
            )

    class _Prompt:
        def __or__(self, _other: object) -> _Chain:
            return _Chain()

    with (
        patch.object(analyzer, "_get_prompt", new=AsyncMock(return_value=_Prompt())),
        patch("app.shared.llm.analyzer.LLMFactory.create", return_value=_LLM()) as factory,
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        content, metadata = await analyzer._invoke_llm(
            formatted_data="{}",
            provider="openai",
            model="gpt-4o-mini",
            byok_key="sk-openai",
            max_output_tokens=128,
            tenant_tier=PricingTier.GROWTH,
        )

    assert content == '{"ok": true}'
    assert metadata == {}
    factory.assert_called_once_with(
        "openai",
        model="gpt-4o-mini",
        api_key="sk-openai",
        max_output_tokens=128,
    )


@pytest.mark.asyncio
async def test_invoke_llm_enterprise_tier_branch_uses_enterprise_fallback_policy() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())

    class _Chain:
        async def ainvoke(self, _payload: dict[str, str]) -> object:
            return SimpleNamespace(content="{}", response_metadata={})

    class _Prompt:
        def __or__(self, _other: object) -> _Chain:
            return _Chain()

    with (
        patch.object(analyzer, "_get_prompt", new=AsyncMock(return_value=_Prompt())),
        patch("app.shared.llm.analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        content, metadata = await analyzer._invoke_llm(
            formatted_data="{}",
            provider="groq",
            model="llama-3.3-70b-versatile",
            byok_key=None,
            tenant_tier=PricingTier.ENTERPRISE,
        )

    assert content == "{}"
    assert metadata == {}


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


@pytest.mark.asyncio
async def test_check_and_alert_anomalies_tenant_slack_lookup_no_service_returns_cleanly() -> None:
    analyzer = FinOpsAnalyzer(MagicMock())
    anomalies = [
        {
            "resource": "ec2-i-456",
            "issue": "cost spike",
            "cost_impact": "$40",
            "severity": "medium",
        }
    ]

    with (
        patch(
            "app.shared.llm.analyzer.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ) as get_tenant_slack,
        patch("app.shared.llm.analyzer.get_slack_service") as get_global_slack,
    ):
        await analyzer._check_and_alert_anomalies(
            {"anomalies": anomalies},
            tenant_id=uuid4(),
            db=AsyncMock(),
        )

    get_tenant_slack.assert_awaited_once()
    get_global_slack.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_logs_shape_limit_and_invocation_failure_paths() -> None:
    llm = MagicMock()
    llm.model_name = "llama-3.3-70b-versatile"
    analyzer = FinOpsAnalyzer(llm)
    usage_summary = _build_usage_summary_with_record()
    tenant_id = uuid4()
    db = AsyncMock()

    def _tier_limit(_tier: object, key: str) -> object | None:
        if key == "llm_output_max_tokens":
            return 512
        if key == "llm_prompt_max_input_tokens":
            return None
        return None

    with (
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
        patch(
            "app.shared.llm.analyzer.get_tenant_tier",
            new=AsyncMock(return_value=PricingTier.PRO),
        ),
        patch.object(
            analyzer,
            "_apply_tier_analysis_shape_limits",
            return_value=(usage_summary, {"records_before": 2, "records_after": 1}),
        ),
        patch("app.shared.llm.analyzer.get_tier_limit", side_effect=_tier_limit),
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=Decimal("0.01")),
        ),
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
        patch.object(
            analyzer,
            "_invoke_llm",
            new=AsyncMock(side_effect=RuntimeError("llm-down")),
        ),
        patch("app.shared.llm.analyzer.logger.info") as info_log,
        patch("app.shared.llm.analyzer.logger.error") as error_log,
    ):
        with pytest.raises(RuntimeError, match="llm-down"):
            await analyzer.analyze(usage_summary, tenant_id=tenant_id, db=db)

    assert any(call.args and call.args[0] == "llm_analysis_shape_limited" for call in info_log.call_args_list)
    assert any(call.args and call.args[0] == "llm_invocation_failed" for call in error_log.call_args_list)


@pytest.mark.asyncio
async def test_analyze_reacquires_tenant_tier_when_initial_lookup_is_none() -> None:
    llm = MagicMock()
    llm.model_name = "llama-3.3-70b-versatile"
    analyzer = FinOpsAnalyzer(llm)
    usage_summary = _build_usage_summary_with_record()
    tenant_id = uuid4()
    db = AsyncMock()

    with (
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
        patch(
            "app.shared.llm.analyzer.get_tenant_tier",
            new=AsyncMock(side_effect=[None, PricingTier.PRO]),
        ) as mock_get_tier,
        patch.object(
            analyzer,
            "_apply_tier_analysis_shape_limits",
            return_value=(usage_summary, {"records_before": 1, "records_after": 1}),
        ),
        patch("app.shared.llm.analyzer.get_tier_limit", return_value=None),
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=Decimal("0.01")),
        ),
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(),
        ),
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
            analyzer,
            "_process_analysis_results",
            new=AsyncMock(return_value={"ok": True}),
        ),
    ):
        result = await analyzer.analyze(usage_summary, tenant_id=tenant_id, db=db)

    assert result == {"ok": True}
    assert mock_get_tier.await_count == 2


@pytest.mark.asyncio
async def test_analyze_anonymous_path_skips_tenant_budget_and_metering_invariants() -> None:
    llm = MagicMock()
    llm.model_name = "llama-3.3-70b-versatile"
    analyzer = FinOpsAnalyzer(llm)
    usage_summary = _build_usage_summary_with_record()

    with (
        patch.object(analyzer, "_check_cache_and_delta", return_value=(None, False)),
        patch(
            "app.shared.llm.analyzer.get_tenant_tier",
            new=AsyncMock(side_effect=AssertionError("tenant tier lookup should not run")),
        ) as mock_get_tier,
        patch(
            "app.shared.llm.analyzer.get_tier_limit",
            side_effect=AssertionError("tier limits should not be read for anonymous analysis"),
        ) as mock_get_tier_limit,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(side_effect=AssertionError("reservation should not run")),
        ) as mock_reserve,
        patch(
            "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(side_effect=AssertionError("metered usage record should not run")),
        ) as mock_record_usage,
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
            analyzer,
            "_process_analysis_results",
            new=AsyncMock(return_value={"ok": True}),
        ),
    ):
        result = await analyzer.analyze(usage_summary, tenant_id=None, db=None)

    assert result == {"ok": True}
    mock_get_tier.assert_not_awaited()
    mock_reserve.assert_not_awaited()
    mock_record_usage.assert_not_awaited()
    mock_get_tier_limit.assert_not_called()
