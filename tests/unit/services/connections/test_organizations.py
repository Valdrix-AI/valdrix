import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from app.shared.connections.organizations import OrganizationsDiscoveryService
from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    # add is synchronous
    db.add = MagicMock()
    return db

@pytest.fixture
def management_connection():
    return AWSConnection(
        id=uuid4(),
        aws_account_id="111111111111",
        role_arn="arn:aws:iam::111111111111:role/ValdrixAccess",
        external_id="vx-123",
        is_management_account=True
    )

@pytest.mark.asyncio
async def test_sync_accounts_non_management(mock_db):
    """Should skip sync if connection is not a management account."""
    conn = AWSConnection(is_management_account=False)
    
    with patch("app.shared.connections.organizations.aioboto3.Session") as mock_session:
        await OrganizationsDiscoveryService.sync_accounts(mock_db, conn)
        
        # Should not have created any session
        mock_session.assert_not_called()

@pytest.mark.asyncio
async def test_sync_accounts_success(mock_db, management_connection):
    """Should fetch accounts from AWS and save to DB."""
    
    # STS Mock (Client + Context)
    mock_sts_client = MagicMock()
    mock_sts_client.assume_role = AsyncMock(return_value={
        'Credentials': {
            'AccessKeyId': 'ASIA...',
            'SecretAccessKey': 'secret...',
            'SessionToken': 'token...'
        }
    })
    
    mock_sts_ctx = MagicMock()
    mock_sts_ctx.__aenter__ = AsyncMock(return_value=mock_sts_client)
    mock_sts_ctx.__aexit__ = AsyncMock(return_value=None)
    
    # Org Mock (Client + Context)
    mock_org_client = MagicMock() # Use MagicMock so get_paginator is sync
    
    # Mock Paginator
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = _async_iter([
        {
            'Accounts': [
                {'Id': '222222222222', 'Name': 'Member A', 'Email': 'a@example.com'},
                {'Id': '333333333333', 'Name': 'Member B', 'Email': 'b@example.com'},
                {'Id': '111111111111', 'Name': 'Management', 'Email': 'mgmt@example.com'} # Should be skipped
            ]
        }
    ])
    mock_org_client.get_paginator.return_value = mock_paginator
    
    mock_org_ctx = MagicMock()
    mock_org_ctx.__aenter__ = AsyncMock(return_value=mock_org_client)
    mock_org_ctx.__aexit__ = AsyncMock(return_value=None)
    
    # Session Mock
    mock_session = MagicMock()
    mock_session.client.side_effect = [mock_sts_ctx, mock_org_ctx]
    
    with patch("app.shared.connections.organizations.aioboto3.Session", return_value=mock_session):
        # Mock DB Query (No existing accounts)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        count = await OrganizationsDiscoveryService.sync_accounts(mock_db, management_connection)
        
        assert count == 2 
        
        # Verify assume_role called
        mock_sts_client.assume_role.assert_awaited()
        
        # Verify DB interactions
        assert mock_db.add.call_count == 2
    mock_db.commit.assert_awaited()

@pytest.mark.asyncio
async def test_sync_accounts_excludes_management_from_count(mock_db, management_connection):
    """Management account should not be included in discovery count."""
    # STS Mock (Client + Context)
    mock_sts_client = MagicMock()
    mock_sts_client.assume_role = AsyncMock(return_value={
        'Credentials': {
            'AccessKeyId': 'ASIA...',
            'SecretAccessKey': 'secret...',
            'SessionToken': 'token...'
        }
    })
    
    mock_sts_ctx = MagicMock()
    mock_sts_ctx.__aenter__ = AsyncMock(return_value=mock_sts_client)
    mock_sts_ctx.__aexit__ = AsyncMock(return_value=None)
    
    # Org Mock (Client + Context)
    mock_org_client = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = _async_iter([
        {
            'Accounts': [
                {'Id': management_connection.aws_account_id, 'Name': 'Management', 'Email': 'mgmt@example.com'},
                {'Id': '222222222222', 'Name': 'Member A', 'Email': 'a@example.com'},
            ]
        }
    ])
    mock_org_client.get_paginator.return_value = mock_paginator
    
    mock_org_ctx = MagicMock()
    mock_org_ctx.__aenter__ = AsyncMock(return_value=mock_org_client)
    mock_org_ctx.__aexit__ = AsyncMock(return_value=None)
    
    # Session Mock
    mock_session = MagicMock()
    mock_session.client.side_effect = [mock_sts_ctx, mock_org_ctx]
    
    with patch("app.shared.connections.organizations.aioboto3.Session", return_value=mock_session):
        # Mock DB Query (No existing accounts)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        count = await OrganizationsDiscoveryService.sync_accounts(mock_db, management_connection)
        
        assert count == 1

@pytest.mark.asyncio
async def test_sync_accounts_update_existing(mock_db, management_connection):
    """Should update details for existing discovered accounts."""
    
    # STS Mock
    mock_sts_client = MagicMock()
    mock_sts_client.assume_role = AsyncMock(return_value={'Credentials': {'AccessKeyId': 'x', 'SecretAccessKey': 'y', 'SessionToken': 'z'}})
    mock_sts_ctx = MagicMock()
    mock_sts_ctx.__aenter__ = AsyncMock(return_value=mock_sts_client)
    mock_sts_ctx.__aexit__ = AsyncMock(return_value=None)

    # Org Mock
    mock_org_client = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = _async_iter([
        {'Accounts': [{'Id': '222222222222', 'Name': 'Updated Name', 'Email': 'new@example.com'}]}
    ])
    mock_org_client.get_paginator.return_value = mock_paginator
    
    mock_org_ctx = MagicMock()
    mock_org_ctx.__aenter__ = AsyncMock(return_value=mock_org_client)
    mock_org_ctx.__aexit__ = AsyncMock(return_value=None)

    # Session
    mock_session = MagicMock()
    mock_session.client.side_effect = [mock_sts_ctx, mock_org_ctx]
    
    # Existing DB Record
    existing_account = DiscoveredAccount(
        account_id='222222222222', name='Old Name', email='old@example.com'
    )
    
    with patch("app.shared.connections.organizations.aioboto3.Session", return_value=mock_session):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [existing_account]
        mock_db.execute.return_value = mock_result
        
        await OrganizationsDiscoveryService.sync_accounts(mock_db, management_connection)
        
        # Assert updated
        assert existing_account.name == 'Updated Name'
        assert existing_account.email == 'new@example.com'
        
        mock_db.add.assert_not_called()
        mock_db.commit.assert_awaited()

# Helper for async iteration
async def _async_iter(iterable):
    for item in iterable:
        yield item
