import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch
from app.shared.db.session import (
    get_db,
    set_session_tenant_id,
    before_cursor_execute,
    after_cursor_execute,
    check_rls_policy,
)
from app.shared.core.exceptions import ValdrixException


class TestSessionDeep:
    @pytest.mark.asyncio
    async def test_get_db_no_request(self):
        async for session in get_db():
            assert session.info["rls_context_set"] is True
            break

    @pytest.mark.asyncio
    async def test_get_db_with_request_tenant(self):
        mock_request = MagicMock()
        mock_request.state.tenant_id = "tenant-abc"
        async for session in get_db(mock_request):
            assert session.info["rls_context_set"] is True
            break

    @pytest.mark.asyncio
    async def test_set_session_tenant_id(self):
        mock_session = MagicMock()  # Remove spec to avoid strict attribute checks
        mock_session.execute = AsyncMock()
        mock_session.info = {}

        # Correctly mock bind.url so str(url) contains postgresql
        mock_url = MagicMock()
        mock_url.__str__.return_value = "postgresql://localhost"
        mock_session.bind = MagicMock()
        mock_session.bind.url = mock_url

        mock_conn = MagicMock()
        mock_conn.info = {}
        mock_session.connection = AsyncMock(return_value=mock_conn)

        await set_session_tenant_id(mock_session, "tenant-123")
        assert mock_session.info["rls_context_set"] is True
        assert mock_session.execute.called

    def test_before_after_cursor_execute(self):
        mock_conn = MagicMock()
        mock_conn.info = {}
        before_cursor_execute(mock_conn, None, "SELECT 1", None, None, False)
        assert "query_start_time" in mock_conn.info

        mock_conn.info["query_start_time"] = [0.0]
        with patch("time.perf_counter", return_value=1.0):
            with patch("app.shared.db.session.logger") as mock_logger:
                after_cursor_execute(
                    mock_conn, None, "SELECT * FROM large_table", None, None, False
                )
                assert mock_logger.warning.called

    def test_check_rls_policy_exempt(self):
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            from app.shared.core.constants import RLS_EXEMPT_TABLES

            table = RLS_EXEMPT_TABLES[0]
            stmt, params = check_rls_policy(
                MagicMock(), None, f"SELECT * FROM {table}", {}, None, False
            )
            assert stmt.startswith("SELECT")

    def test_check_rls_policy_violation(self):
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            with pytest.raises(ValdrixException) as exc:
                check_rls_policy(
                    mock_conn, None, "SELECT * FROM sensitive_data", {}, None, False
                )
            assert exc.value.code == "rls_enforcement_failed"

    def test_check_rls_policy_allows_transaction_control_statements(self):
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            stmt, params = check_rls_policy(mock_conn, None, "BEGIN", {}, None, False)
            assert stmt == "BEGIN"
            assert params == {}
            stmt2, params2 = check_rls_policy(
                mock_conn, None, "COMMIT", {}, None, False
            )
            assert stmt2 == "COMMIT"
            assert params2 == {}

    @pytest.mark.asyncio
    async def test_check_rls_policy_violation_async(self):
        with patch("app.shared.db.session.settings") as mock_settings:
            mock_settings.TESTING = False
            mock_conn = MagicMock()
            mock_conn.info = {"rls_context_set": False}
            with pytest.raises(ValdrixException) as exc:
                check_rls_policy(
                    mock_conn, None, "SELECT * FROM sensitive_data", {}, None, False
                )
            assert exc.value.code == "rls_enforcement_failed"
