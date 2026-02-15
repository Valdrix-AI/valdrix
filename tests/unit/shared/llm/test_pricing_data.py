import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.llm.pricing_data import ProviderCost, LLM_PRICING, refresh_llm_pricing


class TestProviderCost:
    def test_provider_cost_initialization(self):
        """Test ProviderCost initializes correctly with attributes and dict access."""
        cost = ProviderCost(input=1.0, output=2.0, free_tier_tokens=100)

        # Test attributes
        assert cost.input == 1.0
        assert cost.output == 2.0
        assert cost.free_tier_tokens == 100

        # Test dict access
        assert cost["input"] == 1.0
        assert cost["output"] == 2.0
        assert cost["free_tier_tokens"] == 100

    def test_provider_cost_defaults(self):
        """Test ProviderCost default values."""
        cost = ProviderCost(input=1.0, output=2.0)
        assert cost.free_tier_tokens == 0
        assert cost["free_tier_tokens"] == 0


class TestLLMPricing:
    def test_pricing_structure(self):
        """Test LLM_PRICING has the expected structure."""
        required_providers = ["groq", "google", "openai", "anthropic"]
        for provider in required_providers:
            assert provider in LLM_PRICING
            assert isinstance(LLM_PRICING[provider], dict)
            assert "default" in LLM_PRICING[provider]

    def test_openai_default_pricing_exists(self):
        """Canonical pricing table should include default provider costs."""
        assert "openai" in LLM_PRICING
        assert "default" in LLM_PRICING["openai"]

    def test_pricing_values_are_provider_cost(self):
        """Test that pricing entries are instances of ProviderCost (or at least dicts)."""
        for provider_data in LLM_PRICING.values():
            for model_cost in provider_data.values():
                assert isinstance(model_cost, (ProviderCost, dict))
                assert "input" in model_cost
                assert "output" in model_cost

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_updates_from_db(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            record = SimpleNamespace(
                provider="openai",
                model="gpt-4o",
                input_cost_per_million=1.23,
                output_cost_per_million=4.56,
                free_tier_tokens=789,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            await refresh_llm_pricing(db_session=db_session)

            assert LLM_PRICING["openai"]["gpt-4o"].input == 1.23
            assert LLM_PRICING["openai"]["gpt-4o"].output == 4.56
            assert LLM_PRICING["openai"]["gpt-4o"].free_tier_tokens == 789
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_uses_session_maker(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            record = SimpleNamespace(
                provider="openai",
                model="gpt-4o-mini",
                input_cost_per_million=0.11,
                output_cost_per_million=0.22,
                free_tier_tokens=10,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [record]

            session = MagicMock()
            session.execute = AsyncMock(return_value=result)

            @asynccontextmanager
            async def fake_session_maker():
                yield session

            with patch("app.shared.db.session.async_session_maker", fake_session_maker):
                await refresh_llm_pricing()

            assert LLM_PRICING["openai"]["gpt-4o-mini"].input == 0.11
            assert LLM_PRICING["openai"]["gpt-4o-mini"].output == 0.22
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_no_records(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            result = MagicMock()
            result.scalars.return_value.all.return_value = []

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            await refresh_llm_pricing(db_session=db_session)

            assert LLM_PRICING == original
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_new_provider_sets_default_and_casts(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            record = SimpleNamespace(
                provider="newprov",
                model="m1",
                input_cost_per_million="0.12",
                output_cost_per_million="0.34",
                free_tier_tokens=None,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            await refresh_llm_pricing(db_session=db_session)

            assert LLM_PRICING["newprov"]["m1"].input == 0.12
            assert LLM_PRICING["newprov"]["m1"].output == 0.34
            assert LLM_PRICING["newprov"]["m1"].free_tier_tokens == 0
            assert LLM_PRICING["newprov"]["default"] is LLM_PRICING["newprov"]["m1"]
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_logs_error(self):
        db_session = MagicMock()
        db_session.execute = AsyncMock(side_effect=RuntimeError("db down"))

        with patch("app.shared.llm.pricing_data.logger") as mock_logger:
            await refresh_llm_pricing(db_session=db_session)

            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_skips_missing_keys(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            bad_record = SimpleNamespace(
                provider=None,
                model="gpt-4o",
                input_cost_per_million=1.0,
                output_cost_per_million=2.0,
                free_tier_tokens=0,
            )
            good_record = SimpleNamespace(
                provider="openai",
                model="gpt-4o",
                input_cost_per_million=1.0,
                output_cost_per_million=2.0,
                free_tier_tokens=0,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [bad_record, good_record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            with patch("app.shared.llm.pricing_data.logger") as mock_logger:
                await refresh_llm_pricing(db_session=db_session)
                mock_logger.warning.assert_any_call(
                    "llm_pricing_record_missing_keys",
                    provider=None,
                    model="gpt-4o",
                )

            assert LLM_PRICING["openai"]["gpt-4o"].input == 1.0
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_skips_invalid_costs(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            bad_record = SimpleNamespace(
                provider="openai",
                model="gpt-4o",
                input_cost_per_million="nan",
                output_cost_per_million=2.0,
                free_tier_tokens=0,
            )
            good_record = SimpleNamespace(
                provider="openai",
                model="gpt-4o-mini",
                input_cost_per_million=0.11,
                output_cost_per_million=0.22,
                free_tier_tokens=-5,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [bad_record, good_record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            with patch("app.shared.llm.pricing_data.logger") as mock_logger:
                await refresh_llm_pricing(db_session=db_session)
                mock_logger.warning.assert_any_call(
                    "llm_pricing_record_invalid_cost",
                    provider="openai",
                    model="gpt-4o",
                    input_cost="nan",
                    output_cost=2.0,
                )

            assert LLM_PRICING["openai"]["gpt-4o-mini"].input == 0.11
            assert LLM_PRICING["openai"]["gpt-4o-mini"].free_tier_tokens == 0
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_normalizes_keys_and_default(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            record = SimpleNamespace(
                provider=" NewProv ",
                model=" Default ",
                input_cost_per_million=0.5,
                output_cost_per_million=1.0,
                free_tier_tokens=10,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            await refresh_llm_pricing(db_session=db_session)

            assert "newprov" in LLM_PRICING
            assert "default" in LLM_PRICING["newprov"]
            assert LLM_PRICING["newprov"]["default"].input == 0.5
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)

    @pytest.mark.asyncio
    async def test_refresh_llm_pricing_overrides_existing_default(self):
        original = copy.deepcopy(LLM_PRICING)
        try:
            record = SimpleNamespace(
                provider="openai",
                model="default",
                input_cost_per_million=9.9,
                output_cost_per_million=8.8,
                free_tier_tokens=0,
            )

            result = MagicMock()
            result.scalars.return_value.all.return_value = [record]

            db_session = MagicMock()
            db_session.execute = AsyncMock(return_value=result)

            await refresh_llm_pricing(db_session=db_session)

            assert LLM_PRICING["openai"]["default"].input == 9.9
            assert LLM_PRICING["openai"]["default"].output == 8.8
        finally:
            LLM_PRICING.clear()
            LLM_PRICING.update(original)
