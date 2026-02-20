import pytest
from unittest.mock import MagicMock, patch

from app.tasks.scheduler_tasks import _open_db_session


class DummyAsyncCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_open_db_session_with_context_manager():
    session = MagicMock()
    cm = DummyAsyncCM(session)

    with patch("app.tasks.scheduler_tasks.async_session_maker", return_value=cm):
        async with _open_db_session() as got:
            assert got is session


@pytest.mark.asyncio
async def test_open_db_session_requires_async_context_manager():
    with patch("app.tasks.scheduler_tasks.async_session_maker", return_value=object()):
        with pytest.raises(TypeError):
            async with _open_db_session():
                pass
