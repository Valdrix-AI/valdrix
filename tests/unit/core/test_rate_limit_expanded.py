import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.core.rate_limit import (
    context_aware_key,
    get_analysis_limit,
    check_remediation_rate_limit,
    get_limiter,
    get_redis_client
)
from uuid import uuid4
from types import SimpleNamespace


@pytest.fixture
def mock_request():
    request = SimpleNamespace()
    request.state = SimpleNamespace()
    request.headers = MagicMock()
    return request




def test_context_aware_key_tenant_id(mock_request):
    """Test key extraction from tenant_id in state."""
    tenant_id = str(uuid4())


    mock_request.state.tenant_id = tenant_id
    
    key = context_aware_key(mock_request)
    assert key == f"tenant:{tenant_id}"

def test_context_aware_key_token_hash(mock_request):
    """Test key extraction from Authorization header token."""
    mock_request.state.tenant_id = None
    mock_request.headers = {"Authorization": "Bearer my-secret-token"}
    
    key = context_aware_key(mock_request)
    assert key.startswith("token:")
    assert len(key) == 6 + 16 # "token:" + 16 hex chars

def test_context_aware_key_ip_fallback(mock_request):
    """Test fallback to remote address."""
    mock_request.state.tenant_id = None
    mock_request.headers = {}
    
    with patch("app.shared.core.rate_limit.get_remote_address", return_value="127.0.0.1"):
        key = context_aware_key(mock_request)
        assert key == "127.0.0.1"

def test_get_analysis_limit_tiers(mock_request):
    """Test tiers return correct limit strings."""
    mock_request.state.tier = "pro"
    assert get_analysis_limit(mock_request) == "50/hour"
    
    mock_request.state.tier = "growth"
    assert get_analysis_limit(mock_request) == "10/hour"
    
    mock_request.state.tier = "unknown"
    assert get_analysis_limit(mock_request) == "1/hour"

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_success():
    """Test remediation limit using Redis."""
    tenant_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 5
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        allowed = await check_remediation_rate_limit(tenant_id, "stop_instance", limit=10)
        assert allowed is True
        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_not_called() # Only called on current == 1

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_first_call():
    """Test first call in Redis sets expiry."""
    tenant_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        await check_remediation_rate_limit(tenant_id, "stop_instance")
        mock_redis.expire.assert_called_once()

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_error_fallback():
    """Test fallback to memory when Redis fails."""
    tenant_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = Exception("Redis connection lost")
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        # Should NOT raise, but fallback to memory
        allowed = await check_remediation_rate_limit(tenant_id, "stop_instance", limit=10)
        assert allowed is True

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_memory_fallback():
    """Test remediation limit using memory fallback."""
    tenant_id = "mem-tenant"
    action = "test_action"
    
    # Ensure redis is None
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=None):
        # First call - allowed
        allowed = await check_remediation_rate_limit(tenant_id, action, limit=1)
        assert allowed is True
        
        # Second call - exceeded
        allowed = await check_remediation_rate_limit(tenant_id, action, limit=1)
        assert allowed is False

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_memory_reset():
    """Test memory fallback window reset."""
    tenant_id = "reset-tenant"
    action = "reset_action"
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=None):
        # Initial call
        await check_remediation_rate_limit(tenant_id, action, limit=1)
        
        # Mock time to be 2 hours later
        future_time = time.time() + 7200
        with patch("time.time", return_value=future_time):
            allowed = await check_remediation_rate_limit(tenant_id, action, limit=1)
            assert allowed is True

def test_get_limiter_initialization():
    """Test that limiter is initialized with correct strategy."""
    with patch("app.shared.core.rate_limit._limiter", None):
        limiter = get_limiter()
        assert limiter is not None

def test_setup_rate_limiting():
    """Test standard app setup for rate limiting."""
    app = MagicMock()
    app.state = MagicMock()
    with patch("app.shared.core.rate_limit.get_limiter") as mock_get:
        mock_limiter = MagicMock()
        mock_get.return_value = mock_limiter
        from app.shared.core.rate_limit import setup_rate_limiting
        setup_rate_limiting(app)
        assert app.state.limiter == mock_limiter
        app.add_exception_handler.assert_called_once()

@pytest.mark.asyncio
async def test_get_redis_client_logic():
    """Test redis client lifecycle management."""
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost"
        with patch("app.shared.core.rate_limit.from_url") as mock_from_url:
            mock_from_url.return_value = MagicMock()
            client = get_redis_client()
            assert client is not None
            
            # Test reconnect logic if loop changes
            with patch("asyncio.get_running_loop") as mock_loop:
                mock_loop.return_value = "new_loop"
                client._loop = "old_loop"
                get_redis_client()
                # Should have reset and re-created
                mock_from_url.call_count == 2
