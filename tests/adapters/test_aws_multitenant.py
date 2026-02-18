import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.schemas.costs import CloudUsageSummary, CostRecord
import app.models.llm  # noqa: F401 - Required for SQLAlchemy registry
import app.models.notification_settings  # noqa: F401
import app.models.background_job  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401 - Required for AWSConnection relationship
from app.shared.core.credentials import AWSCredentials
from botocore.exceptions import ClientError, ConnectTimeoutError

# Sample Connection Data
MOCK_CX = AWSCredentials(
    tenant_id="test-tenant",
    account_id="123456789012",
    role_arn="arn:aws:iam::123456789012:role/ValdrixRole",
    external_id="test-external-id",
    region="us-east-1",
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
            "Expiration": datetime.now(timezone.utc) + timedelta(hours=1),
        }
    }

    # Mock the session.client context manager
    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_sts

    with patch.object(adapter, "session", mock_session):
        creds = await adapter.get_credentials()

        assert creds["AccessKeyId"] == "ASIA..."
        assert adapter._temp_credentials is not None
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
    adapter._temp_credentials = {"AccessKeyId": "CACHED"}
    adapter._temp_credentials_expire_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    mock_session = MagicMock()  # Should not be used

    with patch.object(adapter, "session", mock_session):
        creds = await adapter.get_credentials()
        assert creds["AccessKeyId"] == "CACHED"
        mock_session.client.assert_not_called()


@pytest.mark.asyncio
async def test_get_credentials_expired(adapter):
    """Verify credentials are refreshed if expired."""
    # Set expired credentials
    adapter._temp_credentials = {"AccessKeyId": "EXPIRED"}
    adapter._temp_credentials_expire_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    mock_sts = AsyncMock()
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "NEW",
            "Expiration": datetime.now(timezone.utc) + timedelta(hours=1),
        }
    }

    mock_session = MagicMock()
    mock_session.client.return_value.__aenter__.return_value = mock_sts

    with patch.object(adapter, "session", mock_session):
        creds = await adapter.get_credentials()
        assert creds["AccessKeyId"] == "NEW"
        mock_session.client.assert_called_once()


@pytest.mark.asyncio
async def test_verify_connection_invalid_region(adapter):
    with (
        patch("app.shared.adapters.aws_multitenant.get_settings") as mock_settings,
        patch.object(adapter, "get_credentials", new_callable=AsyncMock) as mock_creds,
    ):
        mock_settings.return_value.AWS_SUPPORTED_REGIONS = ["us-west-2"]
        # Set a different region for adapter to trigger failure
        adapter.credentials.region = "eu-central-1"
        assert await adapter.verify_connection() is False
        mock_creds.assert_not_called()
