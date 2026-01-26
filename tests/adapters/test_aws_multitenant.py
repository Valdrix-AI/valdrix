import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
import app.models.llm  # noqa: F401 - Required for SQLAlchemy registry
import app.models.notification_settings  # noqa: F401
import app.models.background_job  # noqa: F401
from app.models.aws_connection import AWSConnection
from botocore.exceptions import ClientError

# Sample Connection Data
MOCK_CX = AWSConnection(
    tenant_id="test-tenant",
    aws_account_id="123456789012",
    role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
    external_id="test-external-id", 
    region="us-east-1"
)

@pytest.fixture
def adapter():
    return MultiTenantAWSAdapter(MOCK_CX)

@pytest.mark.asyncio
async def test_get_credentials_success(adapter):
    """Verify STS AssumeRole credential fetching."""
    mock_sts = AsyncMock()
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIA...",
            "SecretAccessKey": "secret...",
            "SessionToken": "token...",
            "Expiration": datetime.now(timezone.utc) + timedelta(hours=1)
        }
    }

    # Mock the session.client context manager
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_sts
    
    with patch.object(adapter, 'session', mock_session):
        creds = await adapter.get_credentials()
        
        assert creds["AccessKeyId"] == "ASIA..."
        assert adapter._credentials is not None
        mock_sts.assume_role.assert_called_once_with(
            RoleArn=MOCK_CX.role_arn,
            RoleSessionName="ValdrixCostFetch",
            ExternalId=MOCK_CX.external_id,
            DurationSeconds=3600,
        )

@pytest.mark.asyncio
async def test_get_credentials_cached(adapter):
    """Verify credentials are reused if not expired."""
    # Set valid credentials
    adapter._credentials = {"AccessKeyId": "CACHED"}
    adapter._credentials_expire_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    
    mock_session = MagicMock() # Should not be used
    
    with patch.object(adapter, 'session', mock_session):
        creds = await adapter.get_credentials()
        assert creds["AccessKeyId"] == "CACHED"
        mock_session.client.assert_not_called()

@pytest.mark.asyncio
async def test_get_credentials_expired(adapter):
    """Verify credentials are refreshed if expired."""
    # Set expired credentials
    adapter._credentials = {"AccessKeyId": "EXPIRED"}
    adapter._credentials_expire_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    
    mock_sts = AsyncMock()
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "NEW",
            "Expiration": datetime.now(timezone.utc) + timedelta(hours=1)
        }
    }
    
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_sts
    
    with patch.object(adapter, 'session', mock_session):
        creds = await adapter.get_credentials()
        assert creds["AccessKeyId"] == "NEW"
        mock_session.client.assert_called_once()

@pytest.mark.asyncio
async def test_get_daily_costs_success(adapter):
    """Verify Cost Explorer usage fetching."""
    # Mock Credentials
    adapter._credentials = {"AccessKeyId": "TEST", "SecretAccessKey": "SECRET", "SessionToken": "TOKEN"}
    adapter._credentials_expire_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    mock_ce = AsyncMock()
    mock_ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2024-01-01T00:00:00Z"}, 
                "Groups": [{"Keys": ["S3"], "Metrics": {"AmortizedCost": {"Amount": "100.0", "Unit": "USD"}}}]
            }
        ]
    }
    
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ce
    
    with patch.object(adapter, 'session', mock_session):
        results = await adapter.get_daily_costs(datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc))
        
        assert len(results.records) == 1
        assert results.total_cost == Decimal("100.0")
        
        # Verify client calls
        call_kwargs = mock_ce.get_cost_and_usage.call_args[1]
        assert call_kwargs["TimePeriod"]["Start"] == "2024-01-01"
        assert "AmortizedCost" in call_kwargs["Metrics"]

@pytest.mark.asyncio
async def test_get_daily_costs_pagination(adapter):
    """Verify Cost Explorer pagination."""
    adapter._credentials = {"AccessKeyId": "TEST", "SecretAccessKey": "SECRET", "SessionToken": "TOKEN"}
    adapter._credentials_expire_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    mock_ce = AsyncMock()
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ce
    
    with patch.object(adapter, 'session', mock_session):
        # Create full mock response for page 1
        mock_ce.get_cost_and_usage.side_effect = [
            {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2024-01-01T00:00:00Z"},
                    "Groups": [{"Keys": ["S3"], "Metrics": {"AmortizedCost": {"Amount": "100"}}}]
                }],
                "NextPageToken": "page2"
            },
            {
                "ResultsByTime": [{
                    "TimePeriod": {"Start": "2024-01-02T00:00:00Z"},
                    "Groups": [{"Keys": ["EC2"], "Metrics": {"AmortizedCost": {"Amount": "50"}}}]
                }],
            }
        ]
        results = await adapter.get_daily_costs(datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc))
        assert len(results.records) == 2
        assert results.total_cost == Decimal("150")
        assert mock_ce.get_cost_and_usage.call_count == 2

@pytest.mark.asyncio
async def test_get_daily_costs_error_handling(adapter):
    """Verify AdapterError is raised on CE failure."""
    from app.shared.core.exceptions import AdapterError
    
    adapter._credentials = {"AccessKeyId": "TEST", "SecretAccessKey": "SECRET", "SessionToken": "TOKEN"}
    adapter._credentials_expire_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    mock_ce = AsyncMock()
    mock_ce.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Boom"}}, 
        "get_cost_and_usage"
    )
    
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_ce
    
    with patch.object(adapter, 'session', mock_session):
        with pytest.raises(AdapterError) as excinfo:
            await adapter.get_daily_costs(date(2024, 1, 1), date(2024, 1, 2))
        
        assert "Permission denied" in str(excinfo.value)
        assert excinfo.value.code == "AccessDenied"
        assert excinfo.value.details["aws_account"] == MOCK_CX.aws_account_id
