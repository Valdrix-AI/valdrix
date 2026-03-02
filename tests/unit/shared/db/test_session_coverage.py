import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from app.shared.db.session import (
    get_db,
    set_session_tenant_id,
    before_cursor_execute,
    after_cursor_execute,
    check_rls_policy,
)
from app.shared.core.exceptions import ValdricsException


@pytest.mark.asyncio
async def test_get_db_with_request_tenant():
    """Test get_db sets RLS context from request state."""
    mock_request = MagicMock()
    mock_request.state.tenant_id = uuid.uuid4()

    # Session setup: MagicMock for attributes, AsyncMock for methods
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.connection = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.bind = MagicMock()
    mock_session.bind.url = "postgresql://user:pass@localhost/db"
    mock_session.info = {}

    # Mock the context manager behavior of async_session_maker
    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__.return_value = mock_session

    with patch("app.shared.db.session.async_session_maker", mock_maker):
        async for session in get_db(mock_request):
            assert session.info.get("rls_context_set") is True
            mock_session.execute.assert_called()


@pytest.mark.asyncio
async def test_get_db_no_request():
    """Test get_db without request (system mode)."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.connection = AsyncMock()
    mock_session.close = AsyncMock()
    mock_session.info = {}

    mock_maker = MagicMock()
    mock_maker.return_value.__aenter__.return_value = mock_session

    with patch("app.shared.db.session.async_session_maker", mock_maker):
        async for session in get_db(None):
            assert session.info.get("rls_context_set") is True


@pytest.mark.asyncio
async def test_set_session_tenant_id():
    """Test set_session_tenant_id sets context on session and connection."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.connection = AsyncMock(return_value=MagicMock(info={}))
    mock_session.bind = MagicMock()
    mock_session.bind.url = "postgresql://user:pass@localhost/db"
    mock_session.info = {}

    tenant_id = uuid.uuid4()

    await set_session_tenant_id(mock_session, tenant_id)
    assert mock_session.info.get("rls_context_set") is True
    mock_session.execute.assert_called()


def test_slow_query_logging():
    """Test before/after cursor execute for slow query logging."""
    mock_conn = MagicMock()
    mock_conn.info = {}

    # Start timer
    before_cursor_execute(mock_conn, None, "SELECT * FROM large_table", (), None, False)
    assert "query_start_time" in mock_conn.info

    # Mock a long duration by manually adjusting start time
    import time

    mock_conn.info["query_start_time"] = [time.perf_counter() - 1.0]  # 1s ago

    with patch("app.shared.db.session.logger") as mock_logger:
        after_cursor_execute(
            mock_conn, None, "SELECT * FROM large_table", (), None, False
        )
        mock_logger.warning.assert_called_with(
            "slow_query_detected",
            duration_seconds=pytest.approx(1.0, rel=0.1),
            threshold_seconds=pytest.approx(0.2, rel=0.1),
            statement="SELECT * FROM large_table",
            parameters=None,
        )


def test_check_rls_policy_violation():
    """Test RLS policy enforcement fails when context is False."""
    mock_conn = MagicMock()
    mock_conn.info = {"rls_context_set": False}

    with patch("app.shared.db.session.settings") as mock_settings:
        mock_settings.TESTING = False  # Force enforcement logic

        with pytest.raises(ValdricsException) as exc:
            check_rls_policy(
                mock_conn, None, "SELECT * FROM sensitive_data", (), None, False
            )

        assert exc.value.code == "rls_enforcement_failed"


def test_check_rls_policy_exempt():
    """Test RLS policy doesn't block exempt tables."""
    mock_conn = MagicMock()
    mock_conn.info = {"rls_context_set": False}

    with patch("app.shared.db.session.settings") as mock_settings:
        mock_settings.TESTING = False

        # Should not raise for exempt table
        statement = "SELECT * FROM tenants"
        res_stmt, res_params = check_rls_policy(
            mock_conn, None, statement, (), None, False
        )
        assert res_stmt == statement
