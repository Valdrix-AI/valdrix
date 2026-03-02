import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.connections.organizations import OrganizationsDiscoveryService
from app.models.aws_connection import AWSConnection
from app.models.discovered_account import DiscoveredAccount


class MockPaginator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


class TestOrganizationsDiscoveryDeep:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.add = MagicMock()  # SQLAlchemy add is synchronous
        mock_result = MagicMock()
        db.execute.return_value = mock_result
        return db

    @pytest.mark.asyncio
    async def test_sync_accounts_not_management(self, mock_db):
        conn = AWSConnection(id=uuid4(), is_management_account=False)
        count = await OrganizationsDiscoveryService.sync_accounts(mock_db, conn)
        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_accounts_success(self, mock_db):
        conn = AWSConnection(
            id=uuid4(),
            is_management_account=True,
            role_arn="arn:aws:iam::123456789012:role/Valdrics",
            external_id="ext-123",
            aws_account_id="123456789012",
        )

        mock_sts = MagicMock()
        mock_sts.assume_role = AsyncMock(
            return_value={
                "Credentials": {
                    "AccessKeyId": "AKIA",
                    "SecretAccessKey": "S",
                    "SessionToken": "T",
                }
            }
        )
        mock_sts.__aenter__ = AsyncMock(return_value=mock_sts)
        mock_sts.__aexit__ = AsyncMock()

        mock_org = MagicMock()
        mock_org.__aenter__ = AsyncMock(return_value=mock_org)
        mock_org.__aexit__ = AsyncMock()

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = MockPaginator(
            [
                {
                    "Accounts": [
                        {"Id": "098765432109", "Name": "Member1", "Email": "m1@test.ai"}
                    ]
                }
            ]
        )
        mock_org.get_paginator.return_value = mock_paginator
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        with patch("aioboto3.Session") as mock_session_class:
            mock_session = mock_session_class.return_value
            mock_session.client.side_effect = (
                lambda s, **k: mock_sts if s == "sts" else mock_org
            )

            count = await OrganizationsDiscoveryService.sync_accounts(mock_db, conn)
            assert count == 1
            assert mock_db.add.called
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_sync_accounts_update_existing(self, mock_db):
        conn = AWSConnection(
            id=uuid4(),
            is_management_account=True,
            aws_account_id="123",
            role_arn="arn:aws:role",
            external_id="eid",
        )

        mock_sts = MagicMock()
        mock_sts.assume_role = AsyncMock(
            return_value={
                "Credentials": {
                    "AccessKeyId": "A",
                    "SecretAccessKey": "S",
                    "SessionToken": "T",
                }
            }
        )
        mock_sts.__aenter__ = AsyncMock(return_value=mock_sts)
        mock_sts.__aexit__ = AsyncMock()

        mock_org = MagicMock()
        mock_org.__aenter__ = AsyncMock(return_value=mock_org)
        mock_org.__aexit__ = AsyncMock()

        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = MockPaginator(
            [{"Accounts": [{"Id": "456", "Name": "NewName", "Email": "new@test.ai"}]}]
        )
        mock_org.get_paginator.return_value = mock_paginator

        existing_acc = DiscoveredAccount(account_id="456", name="OldName")
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            existing_acc
        ]

        with patch("aioboto3.Session") as mock_session_class:
            mock_session = mock_session_class.return_value
            mock_session.client.side_effect = (
                lambda s, **k: mock_sts if s == "sts" else mock_org
            )

            await OrganizationsDiscoveryService.sync_accounts(mock_db, conn)
            assert existing_acc.name == "NewName"

    @pytest.mark.asyncio
    async def test_sync_accounts_exception_handling(self, mock_db):
        conn = AWSConnection(id=uuid4(), is_management_account=True)
        with patch("aioboto3.Session") as mock_session_class:
            mock_session_class.side_effect = Exception("AWS Down")
            count = await OrganizationsDiscoveryService.sync_accounts(mock_db, conn)
            assert count == 0
