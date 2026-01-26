"""
Tests for Circuit Breaker - Remediation Safety

Tests:
1. Circuit breaker states
2. Failure tracking
3. Daily savings budget
4. Recovery behavior
"""

import pytest
from unittest.mock import patch

from app.shared.remediation.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreaker,
    CircuitState,
    CircuitBreakerState,
)


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""
    
    def test_config_default_values(self):
        """Config should have sensible defaults."""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 3
        assert config.recovery_timeout_seconds == 300
        assert config.max_daily_savings_usd == 1000.0
    
    def test_config_custom_values(self):
        """Config should accept custom values."""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout_seconds=600,
            max_daily_savings_usd=5000.0
        )
        
        assert config.failure_threshold == 5
        assert config.recovery_timeout_seconds == 600
        assert config.max_daily_savings_usd == 5000.0


class TestCircuitBreakerState:
    """Test CircuitBreakerState class."""
    
    @pytest.mark.asyncio
    async def test_memory_fallback_get(self):
        """State should fallback to memory when no Redis."""
        with patch('app.shared.remediation.circuit_breaker.settings.REDIS_URL', None):
            state = CircuitBreakerState("tenant-123", redis_client=None)
            
            # Get default
            result = await state.get("missing_key", "default")
            assert result == "default"
    
    @pytest.mark.asyncio
    async def test_memory_fallback_set_get(self):
        """State should store in memory when no Redis."""
        with patch('app.shared.remediation.circuit_breaker.settings.REDIS_URL', None):
            state = CircuitBreakerState("tenant-123", redis_client=None)
            
            await state.set("test_key", "test_value")
            result = await state.get("test_key")
            assert result == "test_value"
    
    @pytest.mark.asyncio
    async def test_memory_fallback_incr(self):
        """State should increment in memory when no Redis."""
        with patch('app.shared.remediation.circuit_breaker.settings.REDIS_URL', None):
            state = CircuitBreakerState("tenant-fallback-incr", redis_client=None)
            
            result1 = await state.incr("counter")
            result2 = await state.incr("counter")
            
            assert result1 == 1
            assert result2 == 2


class TestCircuitBreaker:
    """Test CircuitBreaker class."""
    
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        """Circuit breaker should start closed."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("tenant-123", config=config)
        
        state = await cb.get_state()
        assert state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_can_execute_when_closed(self):
        """Should allow execution when closed."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("tenant-test", config=config)
        
        can_execute = await cb.can_execute()
        assert can_execute is True
    
    @pytest.mark.asyncio
    async def test_record_success_resets_failures(self):
        """Recording success should reset failure count."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("tenant-success", config=config)
        
        # Add some failures
        await cb.state.set("failure_count", 2)
        
        # Record success
        await cb.record_success(savings=50.0)
        
        failure_count = await cb.state.get("failure_count", 0)
        assert failure_count == 0
    
    @pytest.mark.asyncio
    async def test_record_failure_increments_count(self):
        """Recording failure should increment failure count."""
        import uuid
        config = CircuitBreakerConfig()
        cb = CircuitBreaker(f"tenant-failure-incr-{uuid.uuid4()}", config=config)
        
        await cb.record_failure("Test error")
        
        failure_count = await cb.state.get("failure_count", 0)
        assert failure_count == 1
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Circuit should open after threshold failures."""
        import uuid
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker(f"tenant-threshold-open-{uuid.uuid4()}", config=config)
        
        await cb.record_failure("Error 1")
        await cb.record_failure("Error 2")
        
        state = await cb.get_state()
        assert state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        """Reset should clear all state."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("tenant-reset", config=config)
        
        # Set some state
        await cb.state.set("state", CircuitState.OPEN.value)
        await cb.state.set("failure_count", 5)
        
        # Reset
        await cb.reset()
        
        state = await cb.get_state()
        failure_count = await cb.state.get("failure_count", 0)
        
        assert state == CircuitState.CLOSED
        assert failure_count == 0
    
    @pytest.mark.asyncio
    async def test_budget_check(self):
        """Should check daily budget."""
        config = CircuitBreakerConfig(max_daily_savings_usd=100.0)
        cb = CircuitBreaker("tenant-budget", config=config)
        
        # Within budget
        can_exec = await cb.can_execute(estimated_savings=50.0)
        assert can_exec is True
    
    @pytest.mark.asyncio
    async def test_get_status(self):
        """get_status should return complete status dict."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("tenant-status", config=config)
        
        status = await cb.get_status()
        
        assert "tenant_id" in status
        assert "state" in status
        assert "failure_count" in status
        assert "daily_savings_usd" in status
        assert "can_execute" in status
