import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from app.shared.adapters.aws import AWSAdapter
from botocore.exceptions import ClientError


def create_mock_connection():
    """Create a mock AWSConnection for testing."""
    mock_conn = MagicMock()
    mock_conn.role_arn = "arn:aws:iam::123456789012:role/TestRole"
    mock_conn.external_id = "test-external-id"
    mock_conn.region = "us-east-1"
    mock_conn.is_cur_enabled = False
    return mock_conn


@pytest.mark.asyncio
async def test_get_daily_costs_success():
    """Verify successful cost fetch returns CloudUsageSummary with records."""
    # 1. Arrange (Setup the Mock)
    mock_client = AsyncMock()

    # Simulate AWS JSON response
    mock_client.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-01-01", "End": "2026-01-02"},
                "Groups": [
                    {
                        "Keys": ["Amazon EC2", "us-east-1"],
                        "Metrics": {
                            "AmortizedCost": {"Amount": "50.00", "Unit": "USD"},
                            "UnblendedCost": {"Amount": "50.00", "Unit": "USD"},
                            "UsageQuantity": {"Amount": "100", "Unit": "Hours"},
                        },
                    }
                ],
                "Total": {
                    "AmortizedCost": {"Amount": "50.00", "Unit": "USD"},
                    "UnblendedCost": {"Amount": "50.00", "Unit": "USD"},
                },
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

        mock_conn = create_mock_connection()
        adapter = AWSAdapter(connection=mock_conn)

        # 2. Act (Run the code)
        result = await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))

    # 3. Assert (Verify result is CloudUsageSummary)
    assert result is not None
    assert result.provider == "aws"
    # CloudUsageSummary has records and total_cost, not currency directly
    assert hasattr(result, "records")
    assert hasattr(result, "total_cost")
    assert result.total_cost >= 0


@pytest.mark.asyncio
async def test_get_daily_costs_failure():
    """Verify AdapterError is raised on CE failure."""
    from app.shared.core.exceptions import AdapterError

    mock_client = AsyncMock()
    mock_client.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
        "get_cost_and_usage",
    )

    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = None

    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        mock_session.client.return_value = mock_cm

        mock_conn = create_mock_connection()
        adapter = AWSAdapter(connection=mock_conn)

        with pytest.raises(AdapterError) as excinfo:
            await adapter.get_daily_costs(date(2026, 1, 1), date(2026, 1, 2))

        # Error message updated to match production code
        assert "Permission denied" in str(excinfo.value)
