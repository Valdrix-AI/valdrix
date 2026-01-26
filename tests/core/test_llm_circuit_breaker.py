"""
Tests for LLM Circuit Breaker

Covers:
- Circuit state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold triggering
- Recovery testing
- Per-provider isolation
"""

import pytest

from app.shared.llm.circuit_breaker import (
    LLMCircuitBreaker,
    CircuitState,
    CircuitOpenError,
    get_circuit_breaker
)


class TestLLMCircuitBreaker:
    """Tests for LLMCircuitBreaker class."""
    
    def test_initial_state_is_closed(self):
        """New circuits should start closed."""
        breaker = LLMCircuitBreaker()
        circuit = breaker._get_circuit("groq")
        assert circuit.state == CircuitState.CLOSED
    
    def test_is_available_when_closed(self):
        """Closed circuit should be available."""
        breaker = LLMCircuitBreaker()
        assert breaker.is_available("groq") is True
    
    def test_opens_after_failure_threshold(self):
        """Circuit should open after reaching failure threshold."""
        breaker = LLMCircuitBreaker(failure_threshold=3)
        
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        assert breaker.is_available("groq") is True  # Still under threshold
        
        breaker.record_failure("groq")  # Hits threshold
        
        circuit = breaker._get_circuit("groq")
        assert circuit.state == CircuitState.OPEN
        assert breaker.is_available("groq") is False
    
    def test_success_resets_failure_count(self):
        """Successful calls should reset failure count."""
        breaker = LLMCircuitBreaker(failure_threshold=3)
        
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        breaker.record_success("groq")
        
        circuit = breaker._get_circuit("groq")
        assert circuit.failure_count == 0
        assert circuit.state == CircuitState.CLOSED
    
    def test_half_open_after_recovery_timeout(self):
        """Circuit should go half-open after recovery timeout."""
        breaker = LLMCircuitBreaker(failure_threshold=3, recovery_timeout=0)
        
        # Open the circuit
        for _ in range(3):
            breaker.record_failure("groq")
        
        # With zero timeout, should immediately allow a test request
        assert breaker.is_available("groq") is True
        
        circuit = breaker._get_circuit("groq")
        assert circuit.state == CircuitState.HALF_OPEN
    
    def test_closes_after_success_in_half_open(self):
        """Circuit should close after successes in half-open state."""
        breaker = LLMCircuitBreaker(
            failure_threshold=3, 
            success_threshold=2,
            recovery_timeout=0
        )
        
        # Open the circuit
        for _ in range(3):
            breaker.record_failure("groq")
        
        # Trigger half-open
        breaker.is_available("groq")
        
        # Record successes
        breaker.record_success("groq")
        breaker.record_success("groq")
        
        circuit = breaker._get_circuit("groq")
        assert circuit.state == CircuitState.CLOSED
    
    def test_per_provider_isolation(self):
        """Each provider should have independent circuit state."""
        breaker = LLMCircuitBreaker(failure_threshold=2)
        
        # Open groq circuit
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        
        # Gemini should still be available
        assert breaker.is_available("groq") is False
        assert breaker.is_available("google") is True
    
    def test_protect_raises_when_open(self):
        """Protect should raise CircuitOpenError when open."""
        breaker = LLMCircuitBreaker(failure_threshold=1)
        breaker.record_failure("groq")
        
        with pytest.raises(CircuitOpenError):
            with breaker.protect("groq"):
                pass
    
    def test_get_status(self):
        """Status should return all circuit states."""
        breaker = LLMCircuitBreaker()
        breaker.record_success("groq")
        breaker.record_failure("google")
        
        status = breaker.get_status()
        
        assert "groq" in status
        assert "google" in status
        assert status["groq"]["state"] == "closed"
        assert status["google"]["failure_count"] == 1
    
    def test_reset(self):
        """Reset should clear circuit state."""
        breaker = LLMCircuitBreaker(failure_threshold=2)
        
        breaker.record_failure("groq")
        breaker.record_failure("groq")
        assert breaker.is_available("groq") is False
        
        breaker.reset("groq")
        
        assert breaker.is_available("groq") is True
        circuit = breaker._get_circuit("groq")
        assert circuit.failure_count == 0


class TestLLMCircuitBreakerSingleton:
    """Tests for singleton pattern."""
    
    def test_get_circuit_breaker_returns_singleton(self):
        """get_circuit_breaker should return same instance."""
        # Clear singleton for test
        import app.shared.llm.circuit_breaker as cb_module
        cb_module._circuit_breaker = None
        
        breaker1 = get_circuit_breaker()
        breaker2 = get_circuit_breaker()
        
        assert breaker1 is breaker2
