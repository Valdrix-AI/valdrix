import pytest
import uuid
from unittest.mock import MagicMock
from sqlalchemy import text
from app.db.session import get_db, async_session_maker
from app.models.tenant import Tenant

@pytest.mark.asyncio
async def test_rls_session_tagging_request_success():
    """Verify that get_db tags the session as RLS-contextualized when tenant_id is present."""
    mock_request = MagicMock()
    mock_tenant_id = uuid.uuid4()
    mock_request.state.tenant_id = mock_tenant_id
    
    db_gen = get_db(mock_request)
    session = await anext(db_gen)
    
    try:
        assert session.info.get("rls_context_set") is True
        # Verify the DB config actually got set (requires real DB or robust mock)
        # result = await session.execute(text("SELECT current_setting('app.current_tenant_id', true)"))
        # val = result.scalar()
        # assert val == str(mock_tenant_id)
    finally:
        await db_gen.aclose()

@pytest.mark.asyncio
async def test_rls_session_tagging_request_missing_tenant():
    """Verify that get_db tags the session as NOT contextualized when tenant_id is missing in a request."""
    mock_request = MagicMock()
    # No tenant_id on request.state
    del mock_request.state.tenant_id
    
    db_gen = get_db(mock_request)
    session = await anext(db_gen)
    
    try:
        assert session.info.get("rls_context_set") is False
    finally:
        await db_gen.aclose()

@pytest.mark.asyncio
async def test_rls_session_tagging_background_job():
    """Verify that get_db tags the session as safe for background jobs (no request)."""
    # No request provided
    db_gen = get_db(None)
    session = await anext(db_gen)
    
    try:
        assert session.info.get("rls_context_set") is True
    finally:
        await db_gen.aclose()

@pytest.mark.asyncio
async def test_rls_listener_emits_log_on_missing_context():
    """
    Verify that the check_rls_policy listener emits a metric and logs a critical error
    when a query is executed on an un-contextualized request session.
    """
    from unittest.mock import patch
    from app.db.session import get_db
    from sqlalchemy import text
    
    mock_request = MagicMock()
    # Force a request context with no tenant_id
    del mock_request.state.tenant_id
    
    db_gen = get_db(mock_request)
    session = await anext(db_gen)
    
    try:
        # Patch the logger to verify critical was called
        with patch("app.db.session.logger") as mock_logger:
            # Executing a query with RLS FALSE should trigger the listener
            await session.execute(
                text("SELECT 1"), 
                execution_options={"rls_context_set": False}
            )
            
            # Verify logger.critical was called with the expected event
            assert mock_logger.critical.called, "logger.critical should have been called"
            call_kwargs = mock_logger.critical.call_args
            # The listener calls logger.critical("rls_enforcement_bypass_attempt", ...)
            assert call_kwargs[0][0] == "rls_enforcement_bypass_attempt"
    finally:
        await db_gen.aclose()
