
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_async_mock_warning():
    # This simulates what happens in record_usage
    mock_db = AsyncMock()
    # mock_db.execute returns an AsyncMock by default
    result = await mock_db.execute("SELECT 1")
    # result is an AsyncMock. Calling a method on it returns a coroutine.
    # In app code: tenant = result.scalar_one_or_none()
    # In test, if we don't await this, we get a warning.
    result.scalar_one_or_none()
    # val is now a coroutine that is never awaited.
