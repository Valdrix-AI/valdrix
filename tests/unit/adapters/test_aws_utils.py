import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.adapters.aws_utils import (
    map_aws_credentials,
    get_boto_session,
    get_aws_client,
)


def test_map_aws_credentials_camel_to_snake():
    creds = {
        "AccessKeyId": "AKIA",
        "SecretAccessKey": "SECRET",
        "SessionToken": "TOKEN",
    }
    mapped = map_aws_credentials(creds)
    assert mapped["aws_access_key_id"] == "AKIA"
    assert mapped["aws_secret_access_key"] == "SECRET"
    assert mapped["aws_session_token"] == "TOKEN"


def test_map_aws_credentials_snake_to_snake():
    creds = {"aws_access_key_id": "AKIA", "aws_secret_access_key": "SECRET"}
    mapped = map_aws_credentials(creds)
    assert mapped["aws_access_key_id"] == "AKIA"
    assert mapped["aws_secret_access_key"] == "SECRET"


def test_map_aws_credentials_empty():
    assert map_aws_credentials({}) == {}
    assert map_aws_credentials(None) == {}


def test_get_boto_session():
    session = get_boto_session()
    assert session is not None


@pytest.mark.asyncio
@patch("app.shared.adapters.aws_utils.get_boto_session")
async def test_get_aws_client_with_credentials(mock_get_session):
    mock_session = mock_get_session.return_value
    mock_client = AsyncMock()
    mock_session.client.return_value = mock_client

    creds = {"AccessKeyId": "AKIA", "SecretAccessKey": "SECRET"}
    client = await get_aws_client("ec2", credentials=creds)

    assert client == mock_client
    mock_session.client.assert_called_once()
    _, kwargs = mock_session.client.call_args
    assert kwargs["service_name"] == "ec2"
    assert kwargs["aws_access_key_id"] == "AKIA"


@pytest.mark.asyncio
@patch("app.shared.adapters.aws_utils.get_boto_session")
@patch("app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter")
async def test_get_aws_client_with_connection(mock_adapter_class, mock_get_session):
    mock_session = mock_get_session.return_value
    mock_client = AsyncMock()
    mock_session.client.return_value = mock_client

    mock_connection = MagicMock()
    mock_connection.aws_account_id = "123456789012"
    mock_connection.role_arn = "arn:aws:iam::123456789012:role/ValdrixAccessRole"
    mock_connection.external_id = "external-id-123"
    mock_connection.region = "us-west-2"
    mock_connection.cur_bucket_name = "cur-bucket"
    mock_connection.cur_report_name = "cur-report"
    mock_connection.cur_prefix = "cur-prefix"

    mock_adapter = mock_adapter_class.return_value
    mock_adapter.get_credentials = AsyncMock(return_value={"AccessKeyId": "AKIA"})

    client = await get_aws_client("s3", connection=mock_connection)

    assert client == mock_client
    mock_session.client.assert_called_once()
    _, kwargs = mock_session.client.call_args
    assert kwargs["region_name"] == "us-west-2"
    assert kwargs["aws_access_key_id"] == "AKIA"
