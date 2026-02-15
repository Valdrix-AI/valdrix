from unittest.mock import MagicMock, patch
from starlette.datastructures import Headers
from app.shared.core.rate_limit import (
    context_aware_key,
    get_analysis_limit,
    get_redis_client,
)


def mock_request(headers=None, state_attrs=None):
    req = MagicMock()
    req.headers = Headers(headers or {})
    # Properly configure state mock
    state = MagicMock()
    # Explicitly set defaults to None so getattr(state, "tenant_id", None) works as expected
    state.tenant_id = None
    state.tier = None

    if state_attrs:
        for k, v in state_attrs.items():
            setattr(state, k, v)
    req.state = state
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def test_context_aware_key():
    """Test rate limit key generation strategies."""
    # 1. Tenant ID (Highest priority)
    req1 = mock_request(state_attrs={"tenant_id": "tenant-123"})
    assert context_aware_key(req1) == "tenant:tenant-123"

    # 2. Auth Token Hash
    req2 = mock_request(headers={"Authorization": "Bearer some-token-value"})
    # Patch WHERE IT IS IMPORTED
    with patch(
        "app.shared.core.rate_limit.get_remote_address", return_value="127.0.0.1"
    ):
        key = context_aware_key(req2)
        assert key.startswith("token:")
        assert key != "token:some-token-value"  # Should be hashed

    # 3. IP Fallback
    req3 = mock_request(headers={})
    with patch(
        "app.shared.core.rate_limit.get_remote_address", return_value="10.0.0.1"
    ):
        assert context_aware_key(req3) == "10.0.0.1"


def test_get_analysis_limit():
    """Test dynamic rate limits based on tier."""
    # Starter default
    req_default = mock_request()
    limit = get_analysis_limit(req_default)
    # The default for requests with no tier is "starter" -> 2/hour
    assert limit == "2/hour"

    # Tier mapping
    assert get_analysis_limit(mock_request(state_attrs={"tier": "starter"})) == "2/hour"
    assert get_analysis_limit(mock_request(state_attrs={"tier": "pro"})) == "50/hour"
    assert (
        get_analysis_limit(mock_request(state_attrs={"tier": "enterprise"}))
        == "200/hour"
    )

    # Invalid tier -> default
    assert get_analysis_limit(mock_request(state_attrs={"tier": "invalid"})) == "1/hour"
    assert get_analysis_limit(None) == "1/hour"


def test_redis_client_lazy_init():
    """Test lazy loading of redis client."""
    with patch("app.shared.core.rate_limit.get_settings") as mock_settings:
        mock_settings.return_value.REDIS_URL = "redis://localhost:6379"

        with patch("app.shared.core.rate_limit.from_url") as mock_from_url:
            client = get_redis_client()
            assert client is not None
            mock_from_url.assert_called_once()
