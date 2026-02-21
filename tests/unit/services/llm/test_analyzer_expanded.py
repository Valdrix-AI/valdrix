import pytest
import yaml
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.shared.llm.analyzer import FinOpsAnalyzer


@pytest.fixture
def mock_llm():
    return MagicMock()


class TestFinOpsAnalyzerExpanded:
    def test_init_with_prompt_yaml(self, tmp_path):
        prompt_dir = tmp_path / "app/core"
        prompt_dir.mkdir(parents=True)
        prompt_file = prompt_dir / "prompts.yaml"
        prompt_file.write_text(
            yaml.dump({"finops_analysis": {"system": "Custom Prompt"}})
        )

        with (
            patch("os.path.join", return_value=str(prompt_file)),
            patch("os.path.exists", return_value=True),
        ):
            FinOpsAnalyzer(MagicMock())
            # Hit initialization code

    def test_init_with_invalid_yaml(self, tmp_path):
        prompt_file = tmp_path / "prompts.yaml"
        prompt_file.write_text("NOT_YAML: <<<")  # Invalid YAML
        with (
            patch("os.path.join", return_value=str(prompt_file)),
            patch("os.path.exists", return_value=True),
        ):
            FinOpsAnalyzer(MagicMock())
            # Should use fallback prompt

    @pytest.mark.asyncio
    async def test_analyze_cache_hit(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        tenant_id = uuid4()
        summary = MagicMock()

        with patch("app.shared.llm.analyzer.get_cache_service") as mock_cache:
            mock_cache_instance = AsyncMock()
            mock_cache_instance.get_analysis.return_value = {"cached": "data"}
            mock_cache.return_value = mock_cache_instance

            with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
                mock_settings.return_value.ENABLE_DELTA_ANALYSIS = False

                result = await analyzer.analyze(summary, tenant_id=tenant_id)
                assert result == {"cached": "data"}

    @pytest.mark.asyncio
    async def test_check_cache_delta_no_new_data(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        tenant_id = uuid4()
        summary = MagicMock()
        summary.records = []

        with patch("app.shared.llm.analyzer.get_cache_service") as mock_cache:
            mock_cache_instance = AsyncMock()
            mock_cache_instance.get_analysis.return_value = {"records": []}
            mock_cache.return_value = mock_cache_instance

            with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
                mock_settings.return_value.ENABLE_DELTA_ANALYSIS = True
                mock_settings.return_value.DELTA_ANALYSIS_DAYS = 7

                cached, is_delta = await analyzer._check_cache_and_delta(
                    tenant_id, False, summary
                )
                assert is_delta is False

                assert cached == {"records": []}

    @pytest.mark.asyncio
    async def test_setup_client_budget_degradation(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        tenant_id = uuid4()
        db = AsyncMock()

        from app.shared.llm.budget_manager import BudgetStatus

        with patch(
            "app.shared.llm.analyzer.LLMBudgetManager.check_budget",
            AsyncMock(return_value=BudgetStatus.SOFT_LIMIT),
        ):
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = None
            db.execute.return_value = mock_res

            with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
                mock_settings.return_value.LLM_PROVIDER = "groq"

                for provider, expected_model in [
                    ("groq", "llama-3.1-8b-instant"),
                    ("openai", "gpt-4o-mini"),
                    ("google", "gemini-1.5-flash"),
                    ("anthropic", "claude-3-5-haiku"),
                ]:
                    eff_provider, eff_model, byok_key = (
                        await analyzer._setup_client_and_usage(
                            tenant_id, db, provider, None, input_text="test"
                        )
                    )
                    assert eff_provider == provider
                    assert eff_model == expected_model
                    assert byok_key is None

    @pytest.mark.asyncio
    async def test_setup_client_invalid_provider_fallback(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        with patch("app.shared.llm.analyzer.get_settings") as mock_settings:
            mock_settings.return_value.LLM_PROVIDER = "openai"
            provider, _, _ = await analyzer._setup_client_and_usage(
                None, None, "INVALID", None
            )
            assert provider == "openai"

    @pytest.mark.asyncio
    async def test_setup_client_unsupported_model_fallback(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        _, model, _ = await analyzer._setup_client_and_usage(
            None, None, "openai", "UNKNOWN_MODEL"
        )
        assert model == "gpt-4"  # First in VALID_MODELS["openai"]

    @pytest.mark.asyncio
    async def test_check_and_alert_anomalies_slack(self, mock_llm):
        analyzer = FinOpsAnalyzer(mock_llm)
        result = {
            "anomalies": [
                {
                    "resource": "r-1",
                    "issue": "waste",
                    "cost_impact": "$100",
                    "severity": "high",
                }
            ]
        }

        with patch("app.shared.llm.analyzer.get_slack_service") as mock_get_slack:
            mock_slack_instance = AsyncMock()
            mock_get_slack.return_value = mock_slack_instance
            await analyzer._check_and_alert_anomalies(result)
            mock_slack_instance.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_and_alert_no_anomalies(self, mock_llm):
        """No alert should fire if anomalies list is empty."""
        analyzer = FinOpsAnalyzer(mock_llm)
        result = {"anomalies": []}

        with patch("app.shared.llm.analyzer.get_slack_service") as mock_get_slack:
            mock_slack_instance = AsyncMock()
            mock_get_slack.return_value = mock_slack_instance
            await analyzer._check_and_alert_anomalies(result)
            mock_slack_instance.send_alert.assert_not_called()
