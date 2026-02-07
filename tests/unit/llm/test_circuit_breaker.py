import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from app.shared.llm.circuit_breaker import LLMCircuitBreaker, CircuitState, CircuitOpenError

@pytest.fixture
def breaker():
    return LLMCircuitBreaker(failure_threshold=2, recovery_timeout=60)

def test_normal_operation(breaker):
    """Test closed circuit allows requests."""
    assert breaker.is_available("groq")
    with breaker.protect("groq"):
        pass
    breaker.record_success("groq")
    status = breaker._get_circuit("groq")
    assert status.state == CircuitState.CLOSED
    assert status.failure_count == 0

def test_failure_opening(breaker):
    """Test circuit opens after threshold failures."""
    # Fail once
    breaker.record_failure("groq")
    assert breaker.is_available("groq") # Still closed
    
    # Fail twice (threshold)
    breaker.record_failure("groq")
    assert not breaker.is_available("groq") # Open
    
    # Check protection raises
    with pytest.raises(CircuitOpenError):
        with breaker.protect("groq"):
            pass

def test_recovery_flow(breaker):
    """Test Open -> Half-Open -> Closed transition."""
    # Force open
    breaker.record_failure("groq")
    breaker.record_failure("groq")
    circuit = breaker._get_circuit("groq")
    assert circuit.state == CircuitState.OPEN
    
    # Mock time passing: < timeout
    with patch("app.shared.llm.circuit_breaker.datetime") as mock_dt:
        mock_dt.now.return_value = datetime.now(timezone.utc)
        circuit.last_failure_time = datetime.now(timezone.utc)
        assert not breaker.is_available("groq")
        
        # Mock time passing: > timeout
        future = datetime.now(timezone.utc) + timedelta(seconds=61)
        mock_dt.now.return_value = future
        
        # Should transform to half-open
        assert breaker.is_available("groq")
        assert circuit.state == CircuitState.HALF_OPEN
        
        # Success closes it
        breaker.record_success("groq") # Need 2 successes by default config in test?
        # Check fixture: success_threshold=2 (default in class is 2, fixture didn't set it explicitly, 
        # class init def __init__(..., success_threshold=2).
        
        # First success
        assert circuit.state == CircuitState.HALF_OPEN
        
        # Second success
        breaker.record_success("groq")
        assert circuit.state == CircuitState.CLOSED
