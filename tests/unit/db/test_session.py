import pytest
"""
Tests for Database Session Management
"""

from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from app.shared.db.session import (
    get_db,
    before_cursor_execute,
    after_cursor_execute,
    check_rls_policy,
)


@pytest.mark.asyncio
async def test_get_db_yields_session():
    """Test get_db yields an AsyncSession."""
    mock_request = MagicMock(spec=Request)
    mock_request.state.tenant_id = "tenant-1"

    with patch("app.shared.db.session.async_session_maker") as mock_maker:
        mock_session = AsyncMock()
        # Mock bind.url to simulate postgres
        mock_session.bind.url = "postgresql://localhost/db"
        # async_session_maker() returns mock_session
        mock_maker.return_value = mock_session
        # async with mock_session as session: session becomes mock_session
        mock_session.__aenter__.return_value = mock_session

        # Test generator
        db_gen = get_db(mock_request)
        session = await db_gen.__anext__()

        assert session is mock_session
        # Check if RLS context was set
        mock_session.execute.assert_called()

        # Check cleanup
        try:
            await db_gen.__anext__()
        except StopAsyncIteration:
            pass
        mock_session.__aexit__.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_db_no_request():
    """Test get_db works without a request (e.g., background jobs)."""
    with patch("app.shared.db.session.async_session_maker") as mock_maker:
        mock_session = AsyncMock()
        mock_maker.return_value = mock_session
        mock_session.__aenter__.return_value = mock_session

        db_gen = get_db(None)
        session = await db_gen.__anext__()

        assert session is mock_session
        # Should NOT call execute for RLS context
        mock_session.execute.assert_not_called()


def test_before_after_cursor_execute():
    """Test slow query timing logic."""
    mock_conn = MagicMock()
    mock_conn.info = {}
    mock_context = MagicMock()

    before_cursor_execute(mock_conn, None, "SELECT 1", None, mock_context, False)
    assert "query_start_time" in mock_conn.info

    with patch("app.shared.db.session.logger") as mock_logger:
        # Simulate 1s duration
        # We need to mock time.perf_counter() for after_cursor_execute
        # and ensure a value is in mock_conn.info["query_start_time"]
        mock_conn.info["query_start_time"] = [10.0]

        with patch("time.perf_counter", return_value=11.5):
            after_cursor_execute(mock_conn, None, "SELECT 1", None, mock_context, False)
            # Should log as slow query (0.2s threshold)
            mock_logger.warning.assert_called()
            assert any(
                "slow_query_detected" in str(arg)
                for arg in mock_logger.warning.call_args[0]
            )


def test_check_rls_policy_no_leak():
    """Test check_rls_policy permits query when not in request."""
    mock_conn = MagicMock()
    mock_conn.info = {}  # No request_context

    # Should not raise
    check_rls_policy(mock_conn, None, "SELECT 1", None, None, False)
