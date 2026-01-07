import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from app.services.adapters.aws import AWSAdapter
from botocore.exceptions import ClientError

@pytest.mark.asyncio
async def test_get_daily_costs_success():
  # 1. Arrange (Setup the Mock)
  mock_boto = MagicMock()

  # Simulate AWS JSON response
  mock_boto.get_cost_and_usage.return_value = {
    "ResultsByTime": [
      {
        "TimePeriod": {
          "Start": "2026-01-01"},
        "Total": {
          "UnblendedCost": {
            "Amount": "50.00",
          }
        }
      }
    ]
  }

  # Patch 'boto3.client' so when AWSAdapter calls it, it gets our mock
  with patch("boto3.client", return_value=mock_boto):
    adapter = AWSAdapter()
    
    # 2. Act (Run the code)
    result = await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))

  # 3. Assert (Verify result)
  assert len(result) == 1
  assert result[0]["Total"]["UnblendedCost"]["Amount"] == "50.00"

@pytest.mark.asyncio
async def test_get_daily_costs_failure():
  # 1. Arrange: Mark it crash
  mock_boto = MagicMock()
  mock_boto.get_cost_and_usage.side_effect = ClientError(
    {
      "Error": {
        "Code": "AccessDenied",
        "Message": "Access Denied"
      }
    }, "get_cost_and_usage"
  )

  with patch("boto3.client", return_value=mock_boto):
    adapter = AWSAdapter()
    
    # 2. Act (Run the code)
    result = await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))

  # 3. Assert: Should be handled gracefully 
  assert result == []
