import pytest
import time
from unittest.mock import patch
from datetime import datetime, timezone
from app.shared.adapters.aws import AWSAdapter

@pytest.mark.asyncio
async def test_aws_adapter_streaming_performance():
    """
    Benchmark AWS cost streaming with 10,000 mock records.
    Requirement: Should handle >1k records/sec in isolation.
    """
    adapter = AWSAdapter()
    
    # Mocking large dataset
    mock_item = {
        "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
        "Total": {"UnblendedCost": {"Amount": "0.01", "Unit": "USD"}}
    }
    large_dataset = [mock_item] * 10000
    
    with patch.object(adapter, "get_daily_costs", return_value=large_dataset):
        start_time = time.perf_counter()
        
        count = 0
        async for _ in adapter.stream_cost_and_usage(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 2, tzinfo=timezone.utc)
        ):
            count += 1
            
        end_time = time.perf_counter()
        duration = end_time - start_time
        
        throughput = count / duration if duration > 0 else 0
        print(f"\n[Performance] AWS Streaming Throughput: {throughput:.2f} records/sec")
        
        assert count == 10000
        # Target: >5000 records/sec on standard CI/CD runners
        assert throughput > 1000 
