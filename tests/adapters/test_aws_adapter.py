import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from app.shared.adapters.aws import AWSAdapter
from botocore.exceptions import ClientError

@pytest.mark.asyncio
async def test_get_daily_costs_success():
  # 1. Arrange (Setup the Mock)
  mock_client = AsyncMock()

  # Simulate AWS JSON response
  mock_client.get_cost_and_usage.return_value = {
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

  # Mock Context Manager
  mock_cm = MagicMock()
  mock_cm.__aenter__.return_value = mock_client
  mock_cm.__aexit__.return_value = None

  # Patch 'aioboto3.Session'
  with patch("aioboto3.Session") as mock_session_cls:
    mock_session = mock_session_cls.return_value
    mock_session.client.return_value = mock_cm

    adapter = AWSAdapter()
    
    # 2. Act (Run the code)
    result = await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))

  # 3. Assert (Verify result)
  assert len(result) == 1
  assert result[0]["Total"]["UnblendedCost"]["Amount"] == "50.00"

@pytest.mark.asyncio
async def test_get_daily_costs_failure():
    """Verify AdapterError is raised on CE failure."""
    from app.shared.core.exceptions import AdapterError
    
    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, 
        "get_cost_and_usage"
    )

    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.client.return_value = mock_cm

        adapter = AWSAdapter()
        
        with pytest.raises(AdapterError) as excinfo:
            await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))
            
        assert "AWS Cost Explorer fetch failed" in str(excinfo.value)
        assert excinfo.value.code == "AccessDenied"
