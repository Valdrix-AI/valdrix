"""
Tests for CacheService - Upstash Redis integration
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import json
from app.shared.cache import CacheService, get_cache_service


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.fixture
def cache_service(mock_redis):
    with patch("app.shared.core.cache._get_async_client", return_value=mock_redis):
        return CacheService()


@pytest.mark.asyncio
async def test_get_analysis_hit(cache_service, mock_redis):
    """Test cache hit for analysis."""
    tenant_id = uuid4()
    mock_redis.get.return_value = json.dumps({"result": "good"})

    res = await cache_service.get_analysis(tenant_id)
    assert res == {"result": "good"}
    mock_redis.get.assert_called_with(f"analysis:{tenant_id}")


@pytest.mark.asyncio
async def test_get_analysis_miss(cache_service, mock_redis):
    """Test cache miss for analysis."""
    tenant_id = uuid4()
    mock_redis.get.return_value = None

    res = await cache_service.get_analysis(tenant_id)
    assert res is None


@pytest.mark.asyncio
async def test_set_analysis(cache_service, mock_redis):
    """Test setting analysis in cache."""
    tenant_id = uuid4()
    data = {"r": 1}

    await cache_service.set_analysis(tenant_id, data)
    mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_get_cost_data(cache_service, mock_redis):
    """Test getting cached cost data."""
    tenant_id = uuid4()
    date_range = "2026-01"
    mock_redis.get.return_value = json.dumps([{"c": 10}])

    res = await cache_service.get_cost_data(tenant_id, date_range)
    assert res == [{"c": 10}]


@pytest.mark.asyncio
async def test_set_cost_data(cache_service, mock_redis):
    """Test caching cost data."""
    tenant_id = uuid4()
    date_range = "2026-01"
    costs = [{"c": 10}]

    await cache_service.set_cost_data(tenant_id, date_range, costs)
    mock_redis.set.assert_called()


@pytest.mark.asyncio
async def test_invalidate_tenant(cache_service, mock_redis):
    """Test child invalidation."""
    tenant_id = uuid4()
    await cache_service.invalidate_tenant(tenant_id)
    mock_redis.delete.assert_called_with(f"analysis:{tenant_id}")


def test_get_cache_service_singleton():
    """Test singleton pattern."""
    with patch("app.shared.core.cache._cache_service", None):
        s1 = get_cache_service()
        s2 = get_cache_service()
        assert s1 is s2
