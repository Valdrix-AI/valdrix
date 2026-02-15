import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from app.modules.optimization.domain.aws_provider.plugins.compute import (
    IdleInstancesPlugin,
)

from app.shared.llm.guardrails import LLMGuardrails


@pytest.mark.asyncio
async def test_legitimate_cost_data_passes():
    """
    Ensure the sanitization isn't TOO aggressive.
    """
    safe_data = {
        "summary": "Monthly cloud spend report",
        "records": [
            {"service": "S3", "cost": 100, "explanation": "Standard usage"},
            {"service": "EC2", "cost": 500, "explanation": "Production workload"},
        ],
    }

    sanitized = await LLMGuardrails.sanitize_input(safe_data)
    # Comparison check
    assert sanitized == safe_data


@pytest.mark.asyncio
async def test_rate_limiter_stress_5000_instances():
    """
    BE-ZD-2: Verify CloudWatch rate limiting and batching with 5000+ instances.
    """
    plugin = IdleInstancesPlugin()
    mock_session = MagicMock()
    region = "us-east-1"

    # 1. Simulate 5001 instances (requires 11 batches of 500)
    mock_instances = [
        {
            "InstanceId": f"i-{i}",
            "InstanceType": "t3.micro",
            "LaunchTime": datetime.now(timezone.utc),
            "Tags": [],
        }
        for i in range(5001)
    ]

    # Create pages of 1000 instances
    pages_list = []
    for i in range(0, 5001, 1000):
        batch = mock_instances[i : i + 1000]
        pages_list.append({"Reservations": [{"Instances": [inst for inst in batch]}]})

    # 2. Mock EC2
    mock_ec2 = MagicMock()  # Use MagicMock for sync methods
    mock_ec2.__aenter__ = AsyncMock(return_value=mock_ec2)
    mock_ec2.__aexit__ = AsyncMock(return_value=None)

    # Mock paginator correctly for aioboto3
    class MockAsyncIterator:
        def __init__(self, pages):
            self.pages = pages.copy()

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.pages:
                raise StopAsyncIteration
            return self.pages.pop(0)

    class MockPaginator:
        def __init__(self, pages):
            self.pages = pages

        def paginate(self, **kwargs):
            return MockAsyncIterator(self.pages)

    # get_paginator is SYNC in aioboto3
    mock_ec2.get_paginator.side_effect = lambda name: MockPaginator(pages_list)

    # 3. Mock CloudWatch
    mock_cw = MagicMock()
    mock_cw.__aenter__ = AsyncMock(return_value=mock_cw)
    mock_cw.__aexit__ = AsyncMock(return_value=None)
    mock_cw.get_metric_data = AsyncMock(return_value={"MetricDataResults": []})

    # 4. Setup client factory mocks - must return async context managers
    # Need to handle both 'async with self._get_client' and 'async with await self._get_client'
    class AsyncContextManager:
        def __init__(self, client):
            self.client = client

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            pass

        def __await__(self):
            # If used as 'await x', return self so 'async with await x' works
            return self.__aenter__().__await__()

    def get_client_mock(session, service, reg, creds, **kwargs):
        if service == "ec2":
            return AsyncContextManager(mock_ec2)
        if service == "cloudwatch":
            return AsyncContextManager(mock_cw)
        return AsyncContextManager(mock_ec2)  # fallback

    with patch.object(plugin, "_get_client", side_effect=get_client_mock):
        # Patch the limiter to ensure 1req/sec and track duration
        from app.shared.adapters.rate_limiter import RateLimiter

        test_limiter = RateLimiter(rate_per_second=1.0)
        # Ensure it starts empty
        test_limiter.tokens = 0
        test_limiter.last_update = asyncio.get_running_loop().time()

        with patch(
            "app.modules.optimization.adapters.aws.plugins.compute.cloudwatch_limiter",
            test_limiter,
        ):
            start_time = asyncio.get_running_loop().time()

            await plugin.scan(mock_session, region)

            end_time = asyncio.get_running_loop().time()
            duration = end_time - start_time

            # ASSERTIONS
            # 5001 instances = 11 batches of 500
            # Since tokens start at 0, 1st request waits 1s, ..., 11th waits 1s.
            # However, the token refill allows the 2nd, 4th, 6th... to potentially be fast
            # depending on precise timing. 11 calls at 1req/sec should be >= 5s.
            assert mock_cw.get_metric_data.call_count == 11
            assert duration >= 5.0, (
                f"Rate limiter failed: expected >= 5s, got {duration}s"
            )
