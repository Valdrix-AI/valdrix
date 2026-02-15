"""
Targeted tests for app/shared/db/session.py missing coverage line 21
"""

import pytest
import os
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Request

# Set test environment before importing app modules
os.environ["TESTING"] = "true"
os.environ["DB_SSL_MODE"] = "disable"
os.environ["is_production"] = "false"

from app.shared.db.session import get_db


class TestDatabaseSessionMissingCoverage:
    """Test database session management missing coverage."""

    @pytest.mark.asyncio
    async def test_get_db_rls_context_set_failure(self):
        """Test get_db handles RLS context setting failure (line 21)."""
        # Create mock request with tenant_id
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = uuid.uuid4()

        # Mock session and connection
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.bind = MagicMock()
        mock_session.bind.url = "postgresql+asyncpg://test"
        mock_session.execute = AsyncMock(side_effect=Exception("Database error"))
        mock_session.connection = AsyncMock(return_value=AsyncMock())
        mock_session.close = AsyncMock()

        with patch("app.shared.db.session.async_session_maker") as mock_session_maker:
            mock_session_maker.return_value.__aenter__.return_value = mock_session

            with patch("app.shared.db.session.logger") as mock_logger:
                # Use the dependency
                async for session in get_db(mock_request):
                    assert session == mock_session
                    break

                # Verify warning was logged for RLS failure
                mock_logger.warning.assert_called_once()
                assert "rls_context_set_failed" in str(mock_logger.warning.call_args)
