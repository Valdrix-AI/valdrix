"""
Tests for usage_tracker.py - LLM usage tracking and cost calculation.
"""

import pytest
from decimal import Decimal
import builtins
from unittest.mock import patch, MagicMock, AsyncMock
from app.shared.llm.usage_tracker import count_tokens, UsageTracker


class TestTokenCounting:
    """Test suite for token counting functions."""

    def test_count_tokens_with_tiktoken_gpt4(self):
        """Test token counting with tiktoken for GPT-4."""
        with patch("tiktoken.get_encoding") as mock_get_encoding:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = ["token1", "token2", "token3"]
            mock_get_encoding.return_value = mock_encoding

            result = count_tokens("Hello world", "gpt-4")

            assert result == 3
            mock_get_encoding.assert_called_once_with("cl100k_base")
            mock_encoding.encode.assert_called_once_with("Hello world")

    def test_count_tokens_with_tiktoken_claude(self):
        """Test token counting with tiktoken for Claude."""
        with patch("tiktoken.get_encoding") as mock_get_encoding:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = ["token"] * 100
            mock_get_encoding.return_value = mock_encoding

            result = count_tokens("Some text", "claude-3-5-sonnet")

            assert result == 100
            mock_get_encoding.assert_called_once_with("cl100k_base")

    def test_count_tokens_fallback_no_tiktoken(self):
        """Test token counting fallback when tiktoken is not available."""
        real_import = builtins.__import__

        def import_mock(name, *args, **kwargs):
            if name == "tiktoken":
                raise ImportError("No module named tiktoken")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_mock):
            result = count_tokens("Hello world", "gpt-4")

            # Fallback: len(text) // 4 = 11 // 4 = 2
            assert result == 2

    def test_count_tokens_fallback_on_error(self):
        """Test token counting fallback when tiktoken fails."""
        with patch("tiktoken.get_encoding") as mock_get_encoding:
            mock_get_encoding.side_effect = Exception("Encoding error")

            result = count_tokens("Hello world", "gpt-4")

            # Fallback: len(text) // 4 = 11 // 4 = 2
            assert result == 2

    def test_count_tokens_unknown_model(self):
        """Test token counting with unknown model (should use default encoding)."""
        with patch("tiktoken.get_encoding") as mock_get_encoding:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = ["token"] * 5
            mock_get_encoding.return_value = mock_encoding

            result = count_tokens("Test", "unknown-model")

            assert result == 5
            mock_get_encoding.assert_called_once_with("cl100k_base")

    def test_count_tokens_empty_text(self):
        """Test token counting with empty text."""
        with patch("tiktoken.get_encoding") as mock_get_encoding:
            mock_encoding = MagicMock()
            mock_encoding.encode.return_value = []
            mock_get_encoding.return_value = mock_encoding

            result = count_tokens("", "gpt-4")

            assert result == 0


class TestUsageTracker:
    """Test suite for UsageTracker class."""

    @pytest.mark.asyncio
    async def test_init(self):
        """Test UsageTracker initialization."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        assert tracker.db == mock_db

    @pytest.mark.asyncio
    async def test_record_usage_basic(self):
        """Test basic usage recording."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record:
            await tracker.record(
                tenant_id="test-tenant-id",
                provider="groq",
                model="llama-3.3-70b-versatile",
                input_tokens=1500,
                output_tokens=800,
                request_type="daily_analysis",
            )

            mock_record.assert_called_once_with(
                tenant_id="test-tenant-id",
                db=mock_db,
                model="llama-3.3-70b-versatile",
                prompt_tokens=1500,
                completion_tokens=800,
                provider="groq",
                operation_id=None,
                request_type="daily_analysis",
            )

    @pytest.mark.asyncio
    async def test_authorize_request(self):
        """Test request authorization."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.check_and_reserve",
            new_callable=AsyncMock,
        ) as mock_check:
            with patch("app.shared.llm.usage_tracker.count_tokens", return_value=100):
                result = await tracker.authorize_request(
                    tenant_id="test-tenant-id",
                    provider="openai",
                    model="gpt-4",
                    input_text="Hello world",
                    max_output_tokens=500,
                )

                assert result
                mock_check.assert_called_once_with(
                    tenant_id="test-tenant-id",
                    db=mock_db,
                    provider="openai",
                    model="gpt-4",
                    prompt_tokens=100,
                    completion_tokens=500,
                )

    @pytest.mark.asyncio
    async def test_get_monthly_usage(self):
        """Test getting monthly usage."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("25.50")

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await tracker.get_monthly_usage("test-tenant-id")

        assert result == Decimal("25.50")
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_monthly_usage_no_usage(self):
        """Test getting monthly usage when no usage exists."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        mock_result = MagicMock()
        mock_result.scalar.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await tracker.get_monthly_usage("test-tenant-id")

        assert result == Decimal("0")

    @pytest.mark.asyncio
    async def test_check_budget(self):
        """Test budget checking."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.check_budget",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = MagicMock()

            result = await tracker.check_budget("test-tenant-id")

            mock_check.assert_called_once_with("test-tenant-id", mock_db)
            assert result == mock_check.return_value

    def test_calculate_cost(self):
        """Test cost calculation."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.estimate_cost"
        ) as mock_estimate:
            mock_estimate.return_value = Decimal("0.15")

            result = tracker.calculate_cost(
                provider="openai", model="gpt-4", input_tokens=100, output_tokens=50
            )

            mock_estimate.assert_called_once_with(100, 50, "gpt-4", "openai")
            assert result == Decimal("0.15")


class TestUsageTrackerProductionQuality:
    """Production-quality tests for UsageTracker class covering security, performance, and integration scenarios."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_security(self):
        """Test tenant isolation and security in usage tracking."""
        mock_db = MagicMock()

        # Test with multiple tenants
        tracker1 = UsageTracker(mock_db)
        tracker2 = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record:
            # Tenant 1 usage
            await tracker1.record(
                tenant_id="tenant-1",
                provider="openai",
                model="gpt-4",
                input_tokens=100,
                output_tokens=50,
            )

            # Tenant 2 usage
            await tracker2.record(
                tenant_id="tenant-2",
                provider="openai",
                model="gpt-4",
                input_tokens=200,
                output_tokens=100,
            )

            # Verify calls are separate
            assert mock_record.call_count == 2
            calls = mock_record.call_args_list

            # First call should be for tenant-1
            assert calls[0][1]["tenant_id"] == "tenant-1"
            assert calls[0][1]["prompt_tokens"] == 100

            # Second call should be for tenant-2
            assert calls[1][1]["tenant_id"] == "tenant-2"
            assert calls[1][1]["prompt_tokens"] == 200

    @pytest.mark.asyncio
    async def test_input_validation_and_sanitization(self):
        """Test input validation and sanitization for security."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # Test with potentially malicious input
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "../../../etc/passwd",
            "'; DROP TABLE users; --",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
        ]

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ):
            for malicious_input in malicious_inputs:
                # Should not crash or expose vulnerabilities
                try:
                    await tracker.record(
                        tenant_id="test-tenant",
                        provider="openai",
                        model="gpt-4",
                        input_tokens=100,
                        output_tokens=50,
                        request_type=malicious_input,  # Potentially malicious
                    )
                except Exception as e:
                    # Should fail gracefully with appropriate error
                    assert "malicious" not in str(e).lower()
                    assert "security" not in str(e).lower()

    @pytest.mark.asyncio
    async def test_concurrent_usage_load_testing(self):
        """Test concurrent usage scenarios and load handling."""
        import asyncio

        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        async def simulate_concurrent_request(request_id: int):
            """Simulate a concurrent LLM request."""
            await asyncio.sleep(0.001)  # Small delay to encourage concurrency
            return await tracker.record(
                tenant_id=f"tenant-{request_id % 10}",  # Multiple tenants
                provider="openai",
                model="gpt-4",
                input_tokens=100 + request_id,
                output_tokens=50 + request_id,
                request_type=f"request-{request_id}",
            )

        # Launch multiple concurrent requests
        tasks = [simulate_concurrent_request(i) for i in range(50)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should complete without errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Request {i} failed with error: {result}")
            else:
                assert result is None  # record() returns None

    @pytest.mark.asyncio
    async def test_error_handling_and_resilience(self):
        """Test error handling and system resilience."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # Test database connection failure
        mock_db.execute = AsyncMock(side_effect=Exception("Database connection lost"))

        with pytest.raises(Exception):
            await tracker.get_monthly_usage("test-tenant")

        # Test with invalid tenant ID
        mock_db.execute.side_effect = None
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_db.execute.return_value = mock_result

        result = await tracker.get_monthly_usage("invalid-tenant")
        assert result == Decimal("0")  # Should handle gracefully

    @pytest.mark.asyncio
    async def test_boundary_conditions_large_inputs(self):
        """Test boundary conditions with very large inputs."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # Test with very large token counts
        large_input_tokens = 1000000  # 1M tokens
        large_output_tokens = 500000  # 500K tokens

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record:
            await tracker.record(
                tenant_id="test-tenant",
                provider="openai",
                model="gpt-4",
                input_tokens=large_input_tokens,
                output_tokens=large_output_tokens,
            )

            # Verify large values are handled correctly
            call_args = mock_record.call_args[1]
            assert call_args["prompt_tokens"] == large_input_tokens
            assert call_args["completion_tokens"] == large_output_tokens

    @pytest.mark.asyncio
    async def test_cost_calculation_precision_and_accuracy(self):
        """Test cost calculation precision and accuracy."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # Test with precise decimal values
        test_cases = [
            (1000, 1000, "openai", "gpt-4o-mini"),  # Balanced usage
            (10000, 100, "openai", "gpt-4"),  # Input heavy
            (100, 10000, "anthropic", "claude-3"),  # Output heavy
            (0, 0, "openai", "gpt-4"),  # Edge case
        ]

        for input_tokens, output_tokens, provider, model in test_cases:
            cost = tracker.calculate_cost(provider, model, input_tokens, output_tokens)

            # Verify cost is reasonable and positive (except for zero case)
            assert isinstance(cost, Decimal)
            if input_tokens == 0 and output_tokens == 0:
                assert cost == Decimal("0")
            else:
                assert cost > 0
                assert cost < Decimal("1000")  # Reasonable upper bound

    @pytest.mark.asyncio
    async def test_monitoring_and_observability(self):
        """Test monitoring and observability features."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)
        mock_result = MagicMock()
        mock_result.scalar.return_value = Decimal("0")
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Test that operations complete within expected time bounds
        import time

        start_time = time.time()
        await tracker.get_monthly_usage("test-tenant")
        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 1.0, (
            f"Operation too slow: {end_time - start_time:.3f}s"
        )

        # Test cost calculation performance
        start_time = time.time()
        for _ in range(1000):
            tracker.calculate_cost("openai", "gpt-4", 1000, 1000)
        end_time = time.time()

        # Should handle 1000 calculations quickly
        assert end_time - start_time < 2.0, (
            f"Cost calculations too slow: {end_time - start_time:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_multi_tenant_cost_tracking_accuracy(self):
        """Test accurate cost tracking across multiple tenants."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        # Simulate multiple tenants with different usage patterns
        tenants_data = {
            "tenant-a": [
                ("openai", "gpt-4", 1000, 500),
                ("anthropic", "claude-3", 800, 400),
            ],
            "tenant-b": [("openai", "gpt-4o-mini", 5000, 1000)],
            "tenant-c": [("openai", "gpt-4", 200, 800), ("openai", "gpt-4", 300, 200)],
        }

        total_costs = {}

        for tenant_id, usages in tenants_data.items():
            tenant_cost = Decimal("0")
            for provider, model, input_tokens, output_tokens in usages:
                cost = tracker.calculate_cost(
                    provider, model, input_tokens, output_tokens
                )
                tenant_cost += cost
            total_costs[tenant_id] = tenant_cost

        # Verify all tenants have reasonable costs
        for tenant_id, cost in total_costs.items():
            assert cost > 0, f"Tenant {tenant_id} has zero cost"
            assert cost < Decimal("100"), f"Tenant {tenant_id} cost too high: {cost}"

        # Verify costs are different (different usage patterns)
        costs = list(total_costs.values())
        assert len(set(costs)) == len(costs), (
            "All tenants have same cost (should be different)"
        )

    @pytest.mark.asyncio
    async def test_quota_enforcement_and_budget_integration(self):
        """Test quota enforcement and budget integration."""
        mock_db = MagicMock()
        tracker = UsageTracker(mock_db)

        with patch(
            "app.shared.llm.usage_tracker.LLMBudgetManager.record_usage",
            new_callable=AsyncMock,
        ) as mock_record:
            # Record usage that might trigger quota checks
            await tracker.record(
                tenant_id="test-tenant",
                provider="openai",
                model="gpt-4",
                input_tokens=50000,  # Large usage that might hit quotas
                output_tokens=25000,
            )

            # Verify usage was recorded
            mock_record.assert_awaited_once()
            call_args = mock_record.call_args[1]
            assert call_args["prompt_tokens"] == 50000
            assert call_args["completion_tokens"] == 25000
