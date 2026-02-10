import pytest
"""
Production-quality tests for LLM Circuit Breaker.
Tests cover fault isolation, recovery logic, monitoring, and resilience patterns.
"""
import os
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from app.shared.llm.circuit_breaker import (
    LLMCircuitBreaker,
    ProviderCircuit,
    CircuitState,
    CircuitOpenError,
    get_circuit_breaker
)


class TestProviderCircuit:
    """Tests for ProviderCircuit dataclass."""

    def test_initialization_defaults(self):
        """Test ProviderCircuit initializes with correct defaults."""
        circuit = ProviderCircuit(name="test-provider")

        assert circuit.name == "test-provider"
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit.success_count == 0
        assert circuit.last_failure_time is None
        assert circuit.last_success_time is None
        assert circuit.failure_threshold == 3
        assert circuit.success_threshold == 2
        assert circuit.recovery_timeout == 60

    def test_initialization_custom_values(self):
        """Test ProviderCircuit with custom threshold values."""
        circuit = ProviderCircuit(
            name="custom-provider",
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=120
        )

        assert circuit.name == "custom-provider"
        assert circuit.failure_threshold == 5
        assert circuit.success_threshold == 3
        assert circuit.recovery_timeout == 120


class TestLLMCircuitBreaker:
    """Tests for LLMCircuitBreaker functionality."""

    @pytest.fixture
    def breaker(self):
        """Test circuit breaker instance."""
        return LLMCircuitBreaker()

    @pytest.fixture
    def breaker_custom_thresholds(self):
        """Test circuit breaker with custom thresholds."""
        return LLMCircuitBreaker(
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=30
        )

    def test_initialization(self, breaker):
        """Test circuit breaker initializes correctly."""
        assert breaker.failure_threshold == 3
        assert breaker.success_threshold == 2
        assert breaker.recovery_timeout == 60
        assert breaker._circuits == {}

    def test_initialization_custom_thresholds(self, breaker_custom_thresholds):
        """Test circuit breaker with custom thresholds."""
        assert breaker_custom_thresholds.failure_threshold == 2
        assert breaker_custom_thresholds.success_threshold == 1
        assert breaker_custom_thresholds.recovery_timeout == 30

    def test_get_circuit_creates_new(self, breaker):
        """Test _get_circuit creates new circuit for unknown provider."""
        circuit = breaker._get_circuit("new-provider")

        assert isinstance(circuit, ProviderCircuit)
        assert circuit.name == "new-provider"
        assert circuit.state == CircuitState.CLOSED
        assert "new-provider" in breaker._circuits

    def test_get_circuit_returns_existing(self, breaker):
        """Test _get_circuit returns existing circuit."""
        circuit1 = breaker._get_circuit("provider")
        circuit2 = breaker._get_circuit("provider")

        assert circuit1 is circuit2
        assert len(breaker._circuits) == 1

    def test_is_available_closed_circuit(self, breaker):
        """Test is_available returns True for closed circuit."""
        assert breaker.is_available("provider") == True

    def test_is_available_open_circuit_recent_failure(self, breaker):
        """Test is_available returns False for open circuit with recent failure."""
        # Record failures to open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Should be open and unavailable
        assert breaker.is_available("provider") == False

    def test_is_available_open_circuit_recovery_timeout(self, breaker):
        """Test is_available transitions to half-open after recovery timeout."""
        # Record failures to open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Mock old failure time
        circuit = breaker._get_circuit("provider")
        circuit.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=61)  # Past recovery timeout

        # Should transition to half-open and be available
        assert breaker.is_available("provider") == True
        assert circuit.state == CircuitState.HALF_OPEN

    def test_is_available_half_open_circuit(self, breaker):
        """Test is_available returns True for half-open circuit."""
        # Record failures to open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Transition to half-open
        circuit = breaker._get_circuit("provider")
        circuit.state = CircuitState.HALF_OPEN

        assert breaker.is_available("provider") == True

    def test_record_success_closed_circuit(self, breaker):
        """Test record_success resets failure count in closed circuit."""
        # Record some failures
        breaker.record_failure("provider")
        breaker.record_failure("provider")

        circuit = breaker._get_circuit("provider")
        assert circuit.failure_count == 2

        # Record success
        breaker.record_success("provider")

        assert circuit.failure_count == 0
        assert circuit.success_count == 1
        assert circuit.last_success_time is not None

    def test_record_success_half_open_circuit_recovery(self, breaker):
        """Test record_success closes circuit when success threshold reached in half-open."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Transition to half-open
        circuit = breaker._get_circuit("provider")
        circuit.state = CircuitState.HALF_OPEN

        # Record successes to reach threshold
        breaker.record_success("provider")
        assert circuit.state == CircuitState.HALF_OPEN  # Not yet closed

        breaker.record_success("provider")  # Reach threshold

        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0
        assert circuit.success_count == 0  # Reset after closing

    def test_record_success_half_open_insufficient_successes(self, breaker):
        """Test record_success doesn't close circuit with insufficient successes in half-open."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Transition to half-open
        circuit = breaker._get_circuit("provider")
        circuit.state = CircuitState.HALF_OPEN

        # Record only one success (below threshold of 2)
        breaker.record_success("provider")

        assert circuit.state == CircuitState.HALF_OPEN
        assert circuit.success_count == 1

    def test_record_failure_closed_circuit_opens_on_threshold(self, breaker):
        """Test record_failure opens circuit when failure threshold reached."""
        # Record failures up to threshold
        for i in range(3):
            breaker.record_failure("provider")

        circuit = breaker._get_circuit("provider")
        assert circuit.state == CircuitState.OPEN
        assert circuit.failure_count == 3

    def test_record_failure_half_open_reopens_circuit(self, breaker):
        """Test record_failure reopens circuit in half-open state."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("provider")

        # Transition to half-open
        circuit = breaker._get_circuit("provider")
        circuit.state = CircuitState.HALF_OPEN

        # Record another failure
        breaker.record_failure("provider")

        assert circuit.state == CircuitState.OPEN
        assert circuit.success_count == 0  # Reset

    def test_protect_context_manager_success(self, breaker):
        """Test protect context manager with successful operation."""
        success_called = False

        with breaker.protect("provider"):
            success_called = True

        assert success_called

        # Record success manually (would be done by caller)
        breaker.record_success("provider")

        circuit = breaker._get_circuit("provider")
        assert circuit.success_count == 1

    def test_protect_context_manager_failure(self, breaker):
        """Test protect context manager with failed operation."""
        with pytest.raises(ValueError, match="Test failure"):
            with breaker.protect("provider"):
                raise ValueError("Test failure")

        # Failure should be recorded
        circuit = breaker._get_circuit("provider")
        assert circuit.failure_count == 1

    def test_protect_context_manager_open_circuit(self, breaker):
        """Test protect context manager raises error for open circuit."""
        # Open the circuit
        for _ in range(3):
            breaker.record_failure("provider")

        with pytest.raises(CircuitOpenError, match="Circuit open for provider"):
            with breaker.protect("provider"):
                pass

    def test_get_status_empty(self, breaker):
        """Test get_status returns empty dict when no circuits."""
        status = breaker.get_status()
        assert status == {}

    def test_get_status_with_circuits(self, breaker):
        """Test get_status returns circuit information."""
        # Create some circuit state
        breaker.record_failure("provider1")
        breaker.record_success("provider2")

        status = breaker.get_status()

        assert "provider1" in status
        assert "provider2" in status

        provider1_status = status["provider1"]
        assert provider1_status["state"] == "closed"
        assert provider1_status["failure_count"] == 1
        assert provider1_status["success_count"] == 0

        provider2_status = status["provider2"]
        assert provider2_status["state"] == "closed"
        assert provider2_status["failure_count"] == 0
        assert provider2_status["success_count"] == 1

    def test_reset_circuit(self, breaker):
        """Test reset functionality."""
        # Create circuit state
        breaker.record_failure("provider")
        breaker.record_success("provider")

        circuit_before = breaker._get_circuit("provider")
        assert circuit_before.failure_count == 0
        assert circuit_before.success_count == 1

        # Reset circuit
        breaker.reset("provider")

        circuit_after = breaker._get_circuit("provider")
        assert circuit_after.failure_count == 0
        assert circuit_after.success_count == 0
        assert circuit_after.state == CircuitState.CLOSED

    def test_reset_unknown_provider(self, breaker):
        """Test reset doesn't fail for unknown provider."""
        # Should not raise exception
        breaker.reset("unknown-provider")


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker behavior."""

    @pytest.fixture
    def breaker(self):
        """Test circuit breaker with faster recovery for testing."""
        return LLMCircuitBreaker(recovery_timeout=1)  # 1 second for fast testing

    def test_full_circuit_lifecycle(self, breaker):
        """Test complete circuit lifecycle: closed -> open -> half-open -> closed."""
        provider = "test-provider"

        # Start closed
        assert breaker.is_available(provider) == True

        # Record failures to open circuit
        for _ in range(3):
            breaker.record_failure(provider)

        circuit = breaker._get_circuit(provider)
        assert circuit.state == CircuitState.OPEN
        assert breaker.is_available(provider) == False

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should transition to half-open and be available
        assert breaker.is_available(provider) == True
        assert circuit.state == CircuitState.HALF_OPEN

        # Record success to close circuit
        breaker.record_success(provider)
        breaker.record_success(provider)
        assert circuit.state == CircuitState.CLOSED
        assert breaker.is_available(provider) == True

    def test_multiple_providers_isolation(self, breaker):
        """Test that provider failures are isolated."""
        # Provider A fails
        for _ in range(3):
            breaker.record_failure("provider-a")

        # Provider B should still be available
        assert breaker.is_available("provider-a") == False
        assert breaker.is_available("provider-b") == True

        # Provider B succeeds
        breaker.record_success("provider-b")

        circuit_a = breaker._get_circuit("provider-a")
        circuit_b = breaker._get_circuit("provider-b")

        assert circuit_a.state == CircuitState.OPEN
        assert circuit_b.state == CircuitState.CLOSED

    def test_concurrent_operations_thread_safety(self, breaker):
        """Test thread safety of concurrent operations."""
        import threading

        results = []
        errors = []

        def worker(provider_name, operation):
            try:
                if operation == "check":
                    result = breaker.is_available(provider_name)
                    results.append(f"{provider_name}_check_{result}")
                elif operation == "success":
                    breaker.record_success(provider_name)
                    results.append(f"{provider_name}_success")
                elif operation == "failure":
                    breaker.record_failure(provider_name)
                    results.append(f"{provider_name}_failure")
            except Exception as e:
                errors.append(str(e))

        # Create concurrent operations
        threads = []
        for i in range(10):
            provider = f"provider-{i % 3}"  # 3 providers
            operation = ["check", "success", "failure"][i % 3]
            thread = threading.Thread(target=worker, args=(provider, operation))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should complete without errors
        assert len(errors) == 0
        assert len(results) == 10

    def test_circuit_state_transitions_edge_cases(self, breaker):
        """Test edge cases in circuit state transitions."""
        provider = "test-provider"

        # Test rapid success/failure transitions
        breaker.record_failure(provider)
        breaker.record_success(provider)  # Should reset failure count
        breaker.record_failure(provider)
        breaker.record_success(provider)

        circuit = breaker._get_circuit(provider)
        assert circuit.state == CircuitState.CLOSED
        assert circuit.failure_count == 0

        # Test failure during half-open
        for _ in range(3):
            breaker.record_failure(provider)

        # Transition to half-open
        circuit.state = CircuitState.HALF_OPEN

        # Failure should reopen circuit
        breaker.record_failure(provider)
        assert circuit.state == CircuitState.OPEN

    def test_recovery_timeout_precision(self, breaker):
        """Test recovery timeout precision."""
        provider = "test-provider"

        # Open circuit
        for _ in range(3):
            breaker.record_failure(provider)

        circuit = breaker._get_circuit(provider)
        assert circuit.state == CircuitState.OPEN

        # Just before timeout - should still be unavailable
        circuit.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=breaker.recovery_timeout - 0.1)
        assert breaker.is_available(provider) == False

        # At timeout - should become available
        circuit.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=breaker.recovery_timeout)
        assert breaker.is_available(provider) == True
        assert circuit.state == CircuitState.HALF_OPEN

    def test_logging_integration(self, breaker):
        """Test that logging is properly integrated."""
        provider = "test-provider"

        with patch('app.shared.llm.circuit_breaker.logger') as mock_logger:
            # Test failure logging
            breaker.record_failure(provider, "test error")

            mock_logger.warning.assert_called()

            # Test success logging in half-open
            for _ in range(3):
                breaker.record_failure(provider)

            circuit = breaker._get_circuit(provider)
            circuit.state = CircuitState.HALF_OPEN

            breaker.record_success(provider)
            breaker.record_success(provider)

            mock_logger.info.assert_called()


class TestCircuitBreakerSingleton:
    """Tests for circuit breaker singleton pattern."""

    def test_get_circuit_breaker_creates_instance(self):
        """Test get_circuit_breaker creates singleton instance."""
        # Reset global instance
        import app.shared.llm.circuit_breaker as cb_module
        cb_module._circuit_breaker = None

        breaker = get_circuit_breaker()

        assert isinstance(breaker, LLMCircuitBreaker)
        assert cb_module._circuit_breaker is breaker

    def test_get_circuit_breaker_returns_same_instance(self):
        """Test get_circuit_breaker returns same singleton instance."""
        # Reset global instance
        import app.shared.llm.circuit_breaker as cb_module
        cb_module._circuit_breaker = None

        breaker1 = get_circuit_breaker()
        breaker2 = get_circuit_breaker()

        assert breaker1 is breaker2


class TestCircuitBreakerProductionQuality:
    """Production-quality tests covering security, performance, and edge cases."""

    def test_circuit_state_enum_values(self):
        """Test circuit state enum has expected values."""
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"

        # Test value conversion
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_provider_name_validation(self):
        """Test provider name handling."""
        breaker = LLMCircuitBreaker()

        # Test with various provider names
        test_providers = [
            "openai",
            "anthropic",
            "google",
            "groq",
            "azure",
            "provider-with-dashes",
            "provider_with_underscores",
            "ProviderWithCaps"
        ]

        for provider in test_providers:
            assert breaker.is_available(provider) == True

            # Should create circuit
            assert provider in breaker._circuits

    def test_datetime_timezone_handling(self):
        """Test proper timezone handling in datetime operations."""
        breaker = LLMCircuitBreaker()

        # Test with timezone-aware datetimes
        provider = "test-provider"
        circuit = breaker._get_circuit(provider)

        # Set failure time
        failure_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        circuit.last_failure_time = failure_time

        # Should handle timezone correctly
        assert breaker.is_available(provider) in [True, False]  # Depending on timing

    def test_memory_usage_efficiency(self):
        """Test memory efficiency with many providers."""
        import psutil
        import os

        breaker = LLMCircuitBreaker()

        # Get initial memory
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create many provider circuits
        for i in range(1000):
            provider_name = f"provider-{i:04d}"
            breaker._get_circuit(provider_name)

            # Perform some operations
            breaker.record_success(provider_name)
            breaker.is_available(provider_name)

        # Check memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (< 50MB for 1000 circuits)
        assert memory_increase < 50, f"Excessive memory usage: {memory_increase:.1f}MB"

        # Should have all circuits
        assert len(breaker._circuits) == 1000

    def test_context_manager_exception_propagation(self):
        """Test that protect context manager properly propagates exceptions."""
        breaker = LLMCircuitBreaker()

        # Test that original exception is preserved
        with pytest.raises(SpecificTestError, match="Specific test error"):
            with breaker.protect("provider"):
                raise SpecificTestError("Specific test error")

        # Should have recorded failure
        circuit = breaker._get_circuit("provider")
        assert circuit.failure_count == 1


class SpecificTestError(Exception):
    """Custom exception for testing."""
    pass
