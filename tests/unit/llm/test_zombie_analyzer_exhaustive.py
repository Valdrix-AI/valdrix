import pytest
from typing import Dict
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from app.shared.llm.zombie_analyzer import ZombieAnalyzer


@pytest.fixture
def zombie_analyzer():
    with patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings:
        mock_settings.return_value.ZOMBIE_PLUGIN_TIMEOUT_SECONDS = 30
        mock_settings.return_value.ZOMBIE_REGION_TIMEOUT_SECONDS = 120
        yield ZombieAnalyzer(MagicMock())


@pytest.mark.asyncio
async def test_zombie_analyzer_byok_resolution(zombie_analyzer):
    """Test resolution of BYOK providers for different cloud accounts."""
    tenant_id = uuid4()

    # Mock mocks
    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = MagicMock(content='{"resources": []}')
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings,
        patch(
            "app.shared.llm.factory.LLMFactory", new_callable=MagicMock
        ) as mock_factory,
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):  # Patch Guardrails
        mock_settings.return_value.ZOMBIE_PLUGIN_TIMEOUT_SECONDS = 30
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

        # Mock LLM factory
        mock_factory_model = MagicMock()
        mock_factory.create.return_value = mock_factory_model

        # Mock DB
        mock_budget = MagicMock(
            preferred_provider="openai",
            openai_api_key="sk-test",
            preferred_model="gpt-4",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=tenant_id, db=mock_db
        )
        # Verify factory IS called because budget has BYOK key
        mock_factory.create.assert_called()


@pytest.mark.asyncio
async def test_zombie_analyzer_claude_byok(zombie_analyzer):
    """Test resolution of Claude BYOK key."""
    tenant_id = uuid4()

    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = MagicMock(
        content='{"summary": "test", "total_monthly_savings": "$0", "resources": []}'
    )
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.zombie_analyzer.get_settings"),
        patch(
            "app.shared.llm.factory.LLMFactory", new_callable=MagicMock
        ) as mock_factory,
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

        mock_factory_model = MagicMock()
        mock_factory.create.return_value = mock_factory_model

        # Mock DB returning Claude budget
        mock_budget = MagicMock(
            preferred_provider="claude",
            claude_api_key="sk-ant-test",
            preferred_model="claude-3-opus",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=tenant_id, db=mock_db
        )

        # Verify factory called with claude and correct key
        mock_factory.create.assert_called_with("claude", api_key="sk-ant-test")


@pytest.mark.asyncio
async def test_zombie_analyzer_gemini_byok(zombie_analyzer):
    """Test resolution of Gemini BYOK key."""
    tenant_id = uuid4()

    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = MagicMock(
        content='{"summary": "test", "total_monthly_savings": "$0", "resources": []}'
    )
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.zombie_analyzer.get_settings"),
        patch(
            "app.shared.llm.factory.LLMFactory", new_callable=MagicMock
        ) as mock_factory,
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

        mock_factory_model = MagicMock()
        mock_factory.create.return_value = mock_factory_model

        # Mock DB returning Gemini (Google) budget
        mock_budget = MagicMock(
            preferred_provider="google",
            google_api_key="sk-goog-test",
            preferred_model="gemini-pro",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=tenant_id, db=mock_db
        )

        # Verify factory called with google and correct key
        mock_factory.create.assert_called_with("google", api_key="sk-goog-test")


@pytest.mark.asyncio
async def test_zombie_analyzer_malformed_response(zombie_analyzer):
    """Test handling of malformed LLM responses."""
    mock_chain = AsyncMock()
    # Simulate LLM returning bad data
    mock_chain.ainvoke.return_value = MagicMock(content="invalid json")

    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.factory.LLMFactory", new_callable=MagicMock),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):  # Patch guardrails to raise error
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        # validate_output raises ValueError on bad JSON usually
        mock_guardrails.validate_output.side_effect = ValueError("Invalid JSON")

        results = await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=uuid4()
        )
        assert results["summary"] == "Analysis completed but response parsing failed."


@pytest.mark.asyncio
async def test_zombie_analyzer_groq_byok(zombie_analyzer):
    """Test resolution of Groq BYOK key."""
    tenant_id = uuid4()

    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = MagicMock(content='{"resources": []}')
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.zombie_analyzer.get_settings"),
        patch(
            "app.shared.llm.factory.LLMFactory", new_callable=MagicMock
        ) as mock_factory,
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

        mock_factory_model = MagicMock()
        mock_factory.create.return_value = mock_factory_model

        # Mock DB returning Groq budget
        mock_budget = MagicMock(
            preferred_provider="groq",
            groq_api_key="sk-groq-test",
            preferred_model="llama-3",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=tenant_id, db=mock_db
        )

        # Verify factory called with groq and correct key
        mock_factory.create.assert_called_with("groq", api_key="sk-groq-test")


@pytest.mark.asyncio
async def test_metadata_skipping(zombie_analyzer):
    """Test that metadata keys are skipped during flattening."""
    # "region" is in skip_keys
    results = {"region": "us-east-1", "ec2": [{"id": "i-1"}]}

    flattened = zombie_analyzer._flatten_zombies(results)
    assert len(flattened) == 1
    assert flattened[0]["id"] == "i-1"
    # Should not include region as a zombie resource


@pytest.mark.asyncio
async def test_usage_tracking_exception(zombie_analyzer):
    """Test usage tracking exception handling."""
    tenant_id = uuid4()
    mock_llm_client = MagicMock()
    zombie_analyzer = ZombieAnalyzer(
        mock_llm_client
    )  # Re-init to use real methods if needed

    mock_chain = AsyncMock()
    mock_chain.ainvoke.return_value = MagicMock(content='{"resources": []}')
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch("app.shared.llm.zombie_analyzer.UsageTracker") as MockTracker,
        patch("app.shared.llm.factory.LLMFactory", new_callable=MagicMock),
        patch("app.shared.llm.zombie_analyzer.get_settings"),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

        # Mock tracker to raise exception
        mock_tracker_instance = AsyncMock()
        mock_tracker_instance.record.side_effect = Exception("DB Error")
        MockTracker.return_value = mock_tracker_instance

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        # Should not raise exception
        await zombie_analyzer.analyze(
            {"ec2": [{"id": "i-1"}]}, tenant_id=tenant_id, db=mock_db
        )


@pytest.mark.asyncio
async def test_zombie_analyzer_empty_results(zombie_analyzer):
    """Test handling of empty detection results."""
    result = await zombie_analyzer.analyze({})
    assert result["summary"] == "No zombie resources detected."
    assert result["resources"] == []


def test_strip_markdown(zombie_analyzer):
    """Test the _strip_markdown helper method."""
    # It is a protected method, so we access it via the instance
    text = '```json\n{"foo": "bar"}\n```'
    cleaned = zombie_analyzer._strip_markdown(text)
    assert cleaned == '{"foo": "bar"}'

    text_no_md = "just text"
    cleaned = zombie_analyzer._strip_markdown(text_no_md)
    assert cleaned == "just text"
