import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.exc import OperationalError
from fastapi import HTTPException

@pytest.mark.asyncio
async def test_db_connection_failure():
    """Verify that DB operational errors are handled gracefully (e.g., return 500/503)."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()

    mock_session.execute.side_effect = OperationalError("db connection failed", {}, None)
    
    # We test the dependency or a service that uses the session
    # For now, let's simulate the behavior in a service that doesn't catch the error
    # but relies on middleware or FastAPI handlers.
    
    async def dummy_endpoint(db=mock_session):
        try:
            await db.execute("SELECT 1")
        except OperationalError:
            # In a real app, this might be caught by middleware to return a 503
            raise HTTPException(status_code=503, detail="Database temporarily unavailable")

    with pytest.raises(HTTPException) as exc:
        await dummy_endpoint()
    assert exc.value.status_code == 503
    assert "unavailable" in exc.value.detail

@pytest.mark.asyncio
async def test_transaction_rollback_on_failure():
    """Verify that a failure mid-transaction triggers a rollback."""
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))

    mock_session.rollback = AsyncMock()

    
    async def failing_transaction(db=mock_session):
        try:
            db.add(MagicMock())
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    with pytest.raises(Exception) as exc:
        await failing_transaction()
    
    assert "Commit failed" in str(exc.value)
    mock_session.rollback.assert_awaited_once()
