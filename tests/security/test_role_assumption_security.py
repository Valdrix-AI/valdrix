import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.models.aws_connection import AWSConnection


@pytest.mark.asyncio
async def test_adapter_arn_validation():
    """
    Verify that MultiTenantAWSAdapter handles invalid ARNs gracefully.
    """
    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.role_arn = "invalid-arn"
    mock_conn.external_id = "vx-123"

    adapter = MultiTenantAWSAdapter(mock_conn)

    # Mock session
    adapter.session = MagicMock()
    mock_sts = AsyncMock()
    adapter.session.client.return_value.__aenter__.return_value = mock_sts

    from botocore.exceptions import ClientError

    mock_sts.assume_role.side_effect = ClientError(
        {"Error": {"Code": "ValidationError", "Message": "Invalid ARN"}}, "AssumeRole"
    )

    with pytest.raises(Exception) as excinfo:
        await adapter.get_credentials()
    assert "AWS STS AssumeRole failure" in str(excinfo.value)


@pytest.mark.asyncio
async def test_credential_isolation():
    """
    Verify that adapter uses connection details correctly.
    (Issue R3: Security testing for role assumption)
    """
    mock_conn = MagicMock(spec=AWSConnection)
    mock_conn.role_arn = "arn:aws:iam::123456789012:role/ValdrixRole"
    mock_conn.external_id = "vx-abcdef"

    adapter = MultiTenantAWSAdapter(mock_conn)

    # Mock session and sts client
    adapter.session = MagicMock()
    mock_sts = AsyncMock()
    adapter.session.client.return_value.__aenter__.return_value = mock_sts

    # Mock STS response
    mock_sts.assume_role.return_value = {
        "Credentials": {
            "AccessKeyId": "ASIA123",
            "SecretAccessKey": "SECRET123",
            "SessionToken": "TOKEN123",
            "Expiration": datetime.now(timezone.utc),
        }
    }

    creds = await adapter.get_credentials()

    # Verify STS was called with correct parameters
    mock_sts.assume_role.assert_called_once_with(
        RoleArn="arn:aws:iam::123456789012:role/ValdrixRole",
        RoleSessionName="ValdrixCostFetch",
        ExternalId="vx-abcdef",
        DurationSeconds=3600,
    )

    assert creds["AccessKeyId"] == "ASIA123"


def test_external_id_generation():
    """
    Verify that every AWSConnection gets a unique, secure ExternalID.
    """
    id1 = AWSConnection.generate_external_id()
    id2 = AWSConnection.generate_external_id()

    assert id1 != id2
    assert id1.startswith("vx-")
    assert len(id1) == 35  # vx- + 32 hex chars
