import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from types import SimpleNamespace
from uuid import uuid4
from app.shared.core.rate_limit import context_aware_key, get_analysis_limit, check_remediation_rate_limit

@pytest.fixture
def mock_request():
    request = SimpleNamespace()
    request.state = SimpleNamespace()
    request.headers = {}
    return request




def test_context_aware_key_tenant(mock_request):
    tid = uuid4()
    mock_request.state.tenant_id = tid
    key = context_aware_key(mock_request)
    assert key == f"tenant:{tid}"

def test_context_aware_key_token_hash(mock_request):
    mock_request.state = MagicMock(spec=[]) # No tenant_id
    mock_request.headers = {"Authorization": "Bearer my_secret_token"}
    key = context_aware_key(mock_request)
    assert key.startswith("token:")
    assert len(key) == 6 + 16 # "token:" + 16 chars hash

def test_context_aware_key_ip_fallback(mock_request):
    mock_request.state = MagicMock(spec=[])
    mock_request.headers = {}
    with patch("app.shared.core.rate_limit.get_remote_address", return_value="1.2.3.4"):
        key = context_aware_key(mock_request)
        assert key == "1.2.3.4"

def test_get_analysis_limit_tiers(mock_request):
    # Trial
    mock_request.state.tier = "trial"
    assert get_analysis_limit(mock_request) == "1/hour"
    # Growth
    mock_request.state.tier = "growth"
    assert get_analysis_limit(mock_request) == "10/hour"
    # Enterprise
    mock_request.state.tier = "enterprise"
    # Note: the actual code has mapping for enterprise as 200/hour
    assert get_analysis_limit(mock_request) == "200/hour"

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_memory_fallback():
    tenant_id = uuid4()
    # Mock Redis as None to force memory fallback
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=None):
        # Allow 2, then block 3rd
        assert await check_remediation_rate_limit(tenant_id, "delete", limit=2) is True
        assert await check_remediation_rate_limit(tenant_id, "delete", limit=2) is True
        assert await check_remediation_rate_limit(tenant_id, "delete", limit=2) is False

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_success():
    tenant_id = uuid4()
    # Need to import AsyncMock here or use unittest.mock.AsyncMock
    from unittest.mock import AsyncMock
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 1
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        res = await check_remediation_rate_limit(tenant_id, "stop")
        assert res is True
        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_called_once()
@pytest.mark.asyncio
async def test_context_aware_key_hash_exception(mock_request):
    mock_request.state = MagicMock(spec=[])
    mock_request.headers = {"Authorization": "Bearer some_token"}
    # Mock hashlib.sha256 to raise an exception
    with patch("hashlib.sha256", side_effect=Exception("Hash fail")):
        with patch("app.shared.core.rate_limit.get_remote_address", return_value="1.2.3.4"):
            key = context_aware_key(mock_request)
            assert key == "1.2.3.4"

@pytest.mark.asyncio
async def test_get_redis_client_no_url():
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = None
        from app.shared.core.rate_limit import get_redis_client
        assert get_redis_client() is None

@pytest.mark.asyncio
async def test_get_redis_client_loop_change():
    from app.shared.core.rate_limit import get_redis_client
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost"
        with patch("app.shared.core.rate_limit.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_client._loop = "old_loop"
            mock_from_url.return_value = mock_client
            
            # First call creates client
            with patch("asyncio.get_running_loop", return_value="old_loop"):
                client1 = get_redis_client()
                assert client1 == mock_client
            
            # Second call with new loop should reset client
            with patch("asyncio.get_running_loop", return_value="new_loop"):
                with patch("app.shared.core.rate_limit._redis_client", mock_client):
                     client2 = get_redis_client()
                     assert client2 == mock_from_url.return_value
                     assert mock_from_url.call_count == 2

@pytest.mark.asyncio
async def test_setup_rate_limiting():
    from app.shared.core.rate_limit import setup_rate_limiting
    from fastapi import FastAPI
    app = FastAPI()
    setup_rate_limiting(app)
    assert hasattr(app.state, "limiter")

@pytest.mark.asyncio
async def test_rate_limit_decorator_testing_mode():
    from app.shared.core.rate_limit import rate_limit
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.TESTING = True
        decorator = rate_limit("10/minute")
        def dummy(): return "ok"
        wrapped = decorator(dummy)
        assert wrapped == dummy

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_limit_exceeded():
    tenant_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 101 # Above limit
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        # Default limit is 50
        res = await check_remediation_rate_limit(tenant_id, "delete")
        assert res is False

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_redis_error_fallback():
    tenant_id = uuid4()
    mock_redis = AsyncMock()
    mock_redis.incr.side_effect = Exception("Redis connection lost")
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=mock_redis):
        # Should fallback to memory and return True (first attempt)
        res = await check_remediation_rate_limit(tenant_id, "delete")
        assert res is True

@pytest.mark.asyncio
async def test_check_remediation_rate_limit_memory_window_reset():
    tenant_id = "test-tenant"
    action = "cleanup"
    
    with patch("app.shared.core.rate_limit.get_redis_client", return_value=None):
        # Use a very small limit and simulate time pass
        with patch("time.time", side_effect=[1000, 1001, 5000]): # Start, Incr, Reset (1000 + 3600 = 4600 < 5000)
            # First attempt
            assert await check_remediation_rate_limit(tenant_id, action, limit=1) is True
            # Second attempt (same window)
            assert await check_remediation_rate_limit(tenant_id, action, limit=1) is False
            # Third attempt (after 1 hour)
            assert await check_remediation_rate_limit(tenant_id, action, limit=1) is True

@pytest.mark.asyncio
async def test_get_redis_client_runtime_error_reset():
    from app.shared.core.rate_limit import get_redis_client
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost"
        with patch("app.shared.core.rate_limit.from_url") as mock_from_url:
            mock_client = MagicMock()
            with patch("app.shared.core.rate_limit._redis_client", mock_client):
                # This should raise RuntimeError and be caught in line 79
                with patch("asyncio.get_running_loop", side_effect=RuntimeError("No loop")):
                    client = get_redis_client()
                    assert client == mock_from_url.return_value
                    assert mock_from_url.call_count == 1

@pytest.mark.asyncio
async def test_get_redis_client_same_loop():
    from app.shared.core.rate_limit import get_redis_client
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost"
        with patch("app.shared.core.rate_limit.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_client._loop = "current_loop"
            
            with patch("app.shared.core.rate_limit._redis_client", mock_client):
                with patch("asyncio.get_running_loop", return_value="current_loop"):
                    client = get_redis_client()
                    assert client == mock_client
                    assert mock_from_url.call_count == 0
