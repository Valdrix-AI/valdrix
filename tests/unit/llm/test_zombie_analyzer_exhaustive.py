import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import date, datetime, timezone, timedelta
from app.shared.llm.zombie_analyzer import ZombieAnalyzer
from app.shared.core.pricing import PricingTier


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
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(return_value=None),
        ),
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
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(return_value=None),
        ),
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

        # Verify factory called with claude, preferred model, and correct key
        mock_factory.create.assert_called_with(
            "claude",
            model="claude-3-opus",
            api_key="sk-ant-test",
            max_output_tokens=512,
        )


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
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(return_value=None),
        ),
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

        # Verify factory called with google, preferred model, and correct key
        mock_factory.create.assert_called_with(
            "google",
            model="gemini-pro",
            api_key="sk-goog-test",
            max_output_tokens=512,
        )


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
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(return_value=None),
        ),
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

        # Verify factory called with groq, preferred model, and correct key
        mock_factory.create.assert_called_with(
            "groq",
            model="llama-3",
            api_key="sk-groq-test",
            max_output_tokens=512,
        )


@pytest.mark.asyncio
async def test_metadata_skipping(zombie_analyzer):
    """Test that metadata keys are skipped during flattening."""
    # "region" is in skip_keys
    results = {"region": "us-east-1", "ec2": [{"id": "i-1"}]}

    flattened = zombie_analyzer._flatten_zombies(results)
    assert len(flattened) == 1
    assert flattened[0]["id"] == "i-1"
    # Should not include region as a zombie resource


def test_flatten_skips_non_list_non_metadata_categories(zombie_analyzer):
    flattened = zombie_analyzer._flatten_zombies(
        {"idle_instances": [{"id": "i-1"}], "unknown_category": {"id": "x"}}
    )
    assert len(flattened) == 1
    assert flattened[0]["category"] == "idle_instances"


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
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new=AsyncMock(side_effect=Exception("DB Error")),
        ),
        patch("app.shared.llm.factory.LLMFactory", new_callable=MagicMock),
        patch("app.shared.llm.zombie_analyzer.get_settings"),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
    ):
        mock_guardrails.sanitize_input = AsyncMock(return_value=[])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"resources": []}
        )

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


@pytest.mark.asyncio
async def test_zombie_analyzer_propagates_user_id_to_budget_and_usage(zombie_analyzer):
    tenant_id = uuid4()
    user_id = uuid4()
    mock_db = AsyncMock()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(
        return_value=MagicMock(
            content='{"summary":"ok","resources":[]}',
            response_metadata={
                "token_usage": {"prompt_tokens": 123, "completion_tokens": 77}
            },
        )
    )
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch(
            "app.shared.llm.zombie_analyzer.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.STARTER,
        ),
        patch.object(
            zombie_analyzer,
            "_get_effective_llm_config",
            new_callable=AsyncMock,
            return_value=("groq", "llama-3.3-70b-versatile", None),
        ),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record_usage,
        patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        mock_guardrails.sanitize_input = AsyncMock(return_value=[{"resource_id": "i-1"}])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"summary": "ok", "resources": []}
        )

        await zombie_analyzer.analyze(
            detection_results={"idle_instances": [{"resource_id": "i-1"}]},
            tenant_id=tenant_id,
            db=mock_db,
            user_id=user_id,
        )

        assert mock_reserve.await_args.kwargs["user_id"] == user_id
        assert mock_reserve.await_args.kwargs["actor_type"] == "user"
        assert mock_record_usage.await_args.kwargs["user_id"] == user_id
        assert mock_record_usage.await_args.kwargs["actor_type"] == "user"


@pytest.mark.asyncio
async def test_zombie_analyzer_applies_tier_shape_limits(zombie_analyzer):
    tenant_id = uuid4()
    mock_db = AsyncMock()
    now = datetime.now(timezone.utc)
    rows = [
        {
            "resource_id": f"r-{idx}",
            "last_activity_at": (now - timedelta(days=idx)).isoformat(),
        }
        for idx in range(120)
    ]
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"summary":"ok","resources":[]}')
    )
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    def _limit_side_effect(tier: PricingTier, key: str):
        mapping = {
            "llm_output_max_tokens": 512,
            "llm_analysis_max_records": 12,
            "llm_analysis_max_window_days": 7,
            "llm_prompt_max_input_tokens": 512,
        }
        return mapping.get(key)

    with (
        patch(
            "app.shared.llm.zombie_analyzer.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.FREE,
        ),
        patch(
            "app.shared.llm.zombie_analyzer.get_tier_limit",
            side_effect=_limit_side_effect,
        ),
        patch.object(
            zombie_analyzer,
            "_get_effective_llm_config",
            new_callable=AsyncMock,
            return_value=("groq", "llama-3.3-70b-versatile", None),
        ),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ),
        patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        mock_guardrails.sanitize_input = AsyncMock(side_effect=lambda payload: payload)
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"summary": "ok", "resources": []}
        )

        await zombie_analyzer.analyze(
            detection_results={"idle_instances": rows},
            tenant_id=tenant_id,
            db=mock_db,
        )

        sanitized_payload = mock_guardrails.sanitize_input.await_args.args[0]
        assert len(sanitized_payload) <= 12
        assert mock_reserve.await_args.kwargs["prompt_tokens"] <= 512


def test_zombie_analyzer_limit_helpers_cover_invalid_and_bounds() -> None:
    assert ZombieAnalyzer._resolve_output_token_ceiling(None) is None
    assert ZombieAnalyzer._resolve_output_token_ceiling("not-an-int") is None
    assert ZombieAnalyzer._resolve_output_token_ceiling(0) is None
    assert ZombieAnalyzer._resolve_output_token_ceiling(12) == 128
    assert ZombieAnalyzer._resolve_output_token_ceiling(99_999) == 32768

    assert ZombieAnalyzer._resolve_positive_limit(None) is None
    assert ZombieAnalyzer._resolve_positive_limit("bad") is None
    assert ZombieAnalyzer._resolve_positive_limit(0, minimum=1) is None
    assert ZombieAnalyzer._resolve_positive_limit(2_000_000, maximum=1000) == 1000


def test_zombie_analyzer_zombie_to_date_variants() -> None:
    now = datetime.now(timezone.utc)
    today = now.date()

    assert ZombieAnalyzer._zombie_to_date({"last_activity_at": now}) == today
    assert ZombieAnalyzer._zombie_to_date({"last_seen_at": today}) == today
    assert ZombieAnalyzer._zombie_to_date({"date": "2026-02-27T00:00:00Z"}) == date(
        2026, 2, 27
    )
    assert ZombieAnalyzer._zombie_to_date({"detected_at": "not-a-date"}) is None


def test_zombie_analyzer_apply_shape_limits_direct_branch_coverage() -> None:
    rows = [
        {
            "resource_id": f"r-{idx}",
            "last_activity_at": f"2026-02-{idx:02d}T00:00:00Z",
        }
        for idx in range(1, 21)
    ]

    def _tier_limit(_: PricingTier, key: str):
        mapping = {
            "llm_analysis_max_window_days": 3650,
            "llm_prompt_max_input_tokens": 400,
            "llm_analysis_max_records": 5,
        }
        return mapping.get(key)

    with patch("app.shared.llm.zombie_analyzer.get_tier_limit", side_effect=_tier_limit):
        limited, limits = ZombieAnalyzer._apply_tier_analysis_shape_limits(
            rows,
            tier=PricingTier.FREE,
        )

    assert limits["records_before"] == 20
    assert limits["max_window_days"] == 3650
    assert limits["max_prompt_tokens"] == 400
    assert limits["max_records"] == 5
    assert limits["records_after"] == 5
    assert [row["resource_id"] for row in limited] == [
        "r-16",
        "r-17",
        "r-18",
        "r-19",
        "r-20",
    ]


def test_zombie_analyzer_apply_shape_limits_no_optional_limits() -> None:
    rows = [{"resource_id": "r-1", "last_activity_at": "2026-02-01T00:00:00Z"}]
    with patch("app.shared.llm.zombie_analyzer.get_tier_limit", return_value=None):
        limited, limits = ZombieAnalyzer._apply_tier_analysis_shape_limits(
            rows,
            tier=PricingTier.FREE,
        )

    assert limited == rows
    assert limits["records_before"] == 1
    assert limits["records_after"] == 1
    assert "max_window_days" not in limits
    assert "max_prompt_tokens" not in limits
    assert "max_records" not in limits


def test_zombie_analyzer_flatten_skips_non_dict_items() -> None:
    analyzer = ZombieAnalyzer(MagicMock())
    flattened = analyzer._flatten_zombies(
        {
            "idle_instances": [{"resource_id": "ok"}, "bad-item", 123],
            "scan_timeout": True,
        }
    )
    assert flattened == [{"resource_id": "ok", "category": "idle_instances"}]


@pytest.mark.asyncio
async def test_zombie_analyzer_get_effective_config_groq_byok_branch() -> None:
    analyzer = ZombieAnalyzer(MagicMock())
    tenant_id = uuid4()
    mock_budget = MagicMock(
        preferred_provider="groq",
        preferred_model="llama-3.3-70b-versatile",
        groq_api_key="gsk-branch-test-key-1234567890",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_budget
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    provider, model, key = await analyzer._get_effective_llm_config(
        db=mock_db,
        tenant_id=tenant_id,
        provider=None,
        model=None,
    )

    assert provider == "groq"
    assert model == "llama-3.3-70b-versatile"
    assert key == "gsk-branch-test-key-1234567890"


@pytest.mark.asyncio
async def test_zombie_analyzer_get_effective_config_unknown_provider_no_byok() -> None:
    analyzer = ZombieAnalyzer(MagicMock())
    tenant_id = uuid4()
    mock_budget = MagicMock(
        preferred_provider="custom-provider",
        preferred_model="custom-model",
        groq_api_key="gsk-unused",
        google_api_key="goog-unused",
        claude_api_key="claude-unused",
        openai_api_key="openai-unused",
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_budget
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result

    provider, model, key = await analyzer._get_effective_llm_config(
        db=mock_db,
        tenant_id=tenant_id,
        provider=None,
        model=None,
    )

    assert provider == "custom-provider"
    assert model == "custom-model"
    assert key is None


@pytest.mark.asyncio
async def test_zombie_analyzer_budget_preauth_without_prompt_cap(zombie_analyzer):
    tenant_id = uuid4()
    mock_db = AsyncMock()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"summary":"ok","resources":[]}')
    )
    zombie_analyzer.prompt = MagicMock()
    zombie_analyzer.prompt.__or__.return_value = mock_chain

    with (
        patch(
            "app.shared.llm.zombie_analyzer.get_tenant_tier",
            new_callable=AsyncMock,
            return_value=PricingTier.FREE,
        ),
        patch(
            "app.shared.llm.zombie_analyzer.get_tier_limit",
            side_effect=lambda *_args, **_kwargs: None,
        ),
        patch.object(
            zombie_analyzer,
            "_get_effective_llm_config",
            new_callable=AsyncMock,
            return_value=("groq", "llama-3.3-70b-versatile", None),
        ),
        patch("app.shared.llm.zombie_analyzer.LLMGuardrails") as mock_guardrails,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_reserve,
        patch(
            "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ),
        patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings,
    ):
        mock_settings.return_value.LLM_PROVIDER = "groq"
        mock_guardrails.sanitize_input = AsyncMock(return_value=[{"resource_id": "i-1"}])
        mock_guardrails.validate_output.return_value = MagicMock(
            model_dump=lambda: {"summary": "ok", "resources": []}
        )

        await zombie_analyzer.analyze(
            detection_results={"idle_instances": [{"resource_id": "i-1"}]},
            tenant_id=tenant_id,
            db=mock_db,
        )

    assert mock_reserve.await_args.kwargs["prompt_tokens"] >= 500
