import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from app.shared.adapters.aws_resource_explorer import AWSResourceExplorerAdapter
from app.models.aws_connection import AWSConnection
from botocore.exceptions import ClientError


@pytest.fixture
def mock_connection():
    conn = MagicMock(spec=AWSConnection)
    conn.tenant_id = "test-tenant-id"
    conn.aws_account_id = "123456789012"
    conn.region = "us-east-1"
    conn.role_arn = "arn:aws:iam::123456789012:role/ValdricsReadOnly"
    conn.external_id = "test-external-id"
    return conn


@pytest.mark.asyncio
async def test_search_resources_success(mock_connection):
    adapter = AWSResourceExplorerAdapter(mock_connection)

    # Create the mock client that acts as an async context manager
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # Mock search paginator
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator

    # Mock the paginate method to return an async iterator
    mock_response = {
        "Resources": [
            {
                "Arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-123456",
                "Service": "ec2",
                "ResourceType": "instance",
                "Region": "us-east-1",
            },
            {
                "Arn": "arn:aws:rds:us-east-1:123456789012:db:mydb",
                "Service": "rds",
                "ResourceType": "db",
                "Region": "us-east-1",
            },
        ]
    }

    class AsyncIterator:
        def __init__(self, items):
            self.items = items

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.items:
                raise StopAsyncIteration
            return self.items.pop(0)

    mock_paginator.paginate.return_value = AsyncIterator([mock_response])

    with patch.object(adapter, "_get_client", return_value=mock_client):
        resources = await adapter.search_resources()

    assert len(resources) == 2
    assert resources[0]["id"] == "i-123456"
    assert resources[1]["resource_type"] == "db"


@pytest.mark.asyncio
async def test_is_enabled_true(mock_connection):
    adapter = AWSResourceExplorerAdapter(mock_connection)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.list_views = AsyncMock(
        return_value={
            "Views": ["arn:aws:resource-explorer-2:us-east-1:123456789012:view/default"]
        }
    )

    with patch.object(adapter, "_get_client", return_value=mock_client):
        enabled = await adapter.is_enabled()

    assert enabled is True


@pytest.mark.asyncio
async def test_is_enabled_false(mock_connection):
    adapter = AWSResourceExplorerAdapter(mock_connection)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.list_views = AsyncMock(return_value={"Views": []})

    with patch.object(adapter, "_get_client", return_value=mock_client):
        enabled = await adapter.is_enabled()

    assert enabled is False


@pytest.mark.asyncio
async def test_search_resources_access_denied(mock_connection):
    adapter = AWSResourceExplorerAdapter(mock_connection)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get_paginator.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "Search"
    )

    with patch.object(adapter, "_get_client", return_value=mock_client):
        resources = await adapter.search_resources()

    assert resources == []
