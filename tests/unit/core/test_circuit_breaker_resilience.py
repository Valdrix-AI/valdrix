import pytest
from typing import Dict
from app.shared.llm.circuit_breaker import LLMCircuitBreaker, CircuitState, CircuitOpenError

def test_circuit_breaker_state_transitions():
    """Verify CLOSED -> OPEN transition after failure threshold."""
    breaker = LLMCircuitBreaker(failure_threshold=2)
    provider = "test_provider"
    
    # First failure
    breaker.record_failure(provider)
    assert breaker.is_available(provider) is True
    
    # Second failure (reaches threshold)
    breaker.record_failure(provider)
    assert breaker.is_available(provider) is False
    assert breaker._get_circuit(provider).state == CircuitState.OPEN

def test_circuit_breaker_recovery_flow():
    """Verify OPEN -> HALF-OPEN -> CLOSED transition."""
    # Short timeout for testing
    breaker = LLMCircuitBreaker(failure_threshold=1, recovery_timeout=0, success_threshold=2)
    provider = "test_provider"
    
    # Trip the circuit
    breaker.record_failure(provider)
    assert breaker._get_circuit(provider).state == CircuitState.OPEN
    
    # Recovery timeout passed (mocked by recovery_timeout=0)
    # Next call to is_available should transition to HALF_OPEN
    assert breaker.is_available(provider) is True
    assert breaker._get_circuit(provider).state == CircuitState.HALF_OPEN
    
    # Record first success in HALF_OPEN
    breaker.record_success(provider)
    assert breaker._get_circuit(provider).state == CircuitState.HALF_OPEN # Still half open
    
    # Record second success
    breaker.record_success(provider)
    assert breaker._get_circuit(provider).state == CircuitState.CLOSED
    assert breaker.is_available(provider) is True

def test_circuit_breaker_protection_decorator():
    """Verify the protect() context manager raises CircuitOpenError when OPEN."""
    breaker = LLMCircuitBreaker(failure_threshold=1)
    provider = "groq"
    
    breaker.record_failure(provider)
    
    with pytest.raises(CircuitOpenError):
        with breaker.protect(provider):
            # This should never be reached
            pass

def test_circuit_breaker_reset():
    """Verify manual reset by admin."""
    breaker = LLMCircuitBreaker(failure_threshold=1)
    breaker.record_failure("test")
    assert breaker.is_available("test") is False
    
    breaker.reset("test")
    assert breaker.is_available("test") is True
    assert breaker._get_circuit("test").state == CircuitState.CLOSED
