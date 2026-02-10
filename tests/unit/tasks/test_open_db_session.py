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
async def test_open_db_session_with_awaitable_context_manager():
    session = MagicMock()
    cm = DummyAsyncCM(session)

    async def maker():
        return cm

    with patch("app.tasks.scheduler_tasks.async_session_maker", return_value=maker()):
        async with _open_db_session() as got:
            assert got is session


@pytest.mark.asyncio
async def test_open_db_session_with_direct_session():
    class DummySession:
        pass

    session = DummySession()

    with patch("app.tasks.scheduler_tasks.async_session_maker", return_value=session):
        async with _open_db_session() as got:
            assert got is session


@pytest.mark.asyncio
async def test_open_db_session_with_awaitable_session():
    class DummySession:
        pass

    session = DummySession()

    async def maker():
        return session

    with patch("app.tasks.scheduler_tasks.async_session_maker", return_value=maker()):
        async with _open_db_session() as got:
            assert got is session
