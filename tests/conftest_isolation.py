import pytest
"""
Test isolation utilities to prevent test interference
"""

import asyncio
from typing import Any, Dict
from unittest.mock import patch


class TestIsolationManager:
    """Manages test isolation to prevent interference between tests."""

    def __init__(self):
        self._patches = []
        self._cleanup_tasks = []

    def add_patch(self, target: str, **kwargs):
        """Add a patch to be cleaned up after test."""
        patch_obj = patch(target, **kwargs)
        self._patches.append(patch_obj)
        return patch_obj

    def add_cleanup_task(self, task):
        """Add a cleanup task to run after test."""
        self._cleanup_tasks.append(task)

    async def setup(self):
        """Setup isolation for a test."""
        # Start all patches
        for patch_obj in self._patches:
            patch_obj.start()

    async def cleanup(self):
        """Cleanup after a test."""
        # Stop all patches
        for patch_obj in self._patches:
            patch_obj.stop()

        # Run cleanup tasks
        for task in self._cleanup_tasks:
            try:
                if asyncio.iscoroutine(task):
                    await task
                else:
                    task()
            except Exception:
                pass  # Ignore cleanup errors

        # Clear lists
        self._patches.clear()
        self._cleanup_tasks.clear()


@pytest.fixture
async def test_isolation():
    """Fixture providing test isolation manager."""
    manager = TestIsolationManager()
    await manager.setup()
    try:
        yield manager
    finally:
        await manager.cleanup()


class MockStateManager:
    """Manages mock state to prevent leakage between tests."""

    _shared_state: Dict[str, Any] = {}

    @classmethod
    def clear_state(cls):
        """Clear all shared state."""
        cls._shared_state.clear()

    @classmethod
    def set_state(cls, key: str, value: Any):
        """Set state value."""
        cls._shared_state[key] = value

    @classmethod
    def get_state(cls, key: str, default: Any = None) -> Any:
        """Get state value."""
        return cls._shared_state.get(key, default)

    @classmethod
    def has_state(cls, key: str) -> bool:
        """Check if state exists."""
        return key in cls._shared_state


@pytest.fixture(autouse=True)
def clear_mock_state():
    """Auto-use fixture to clear mock state between tests."""
    MockStateManager.clear_state()
    yield
    MockStateManager.clear_state()


class AsyncEventLoopManager:
    """Manages asyncio event loop isolation for tests."""

    def __init__(self):
        self._original_loop = None

    def setup_loop_isolation(self):
        """Setup loop isolation."""
        try:
            self._original_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, that's fine
            pass

    def restore_loop(self):
        """Restore original loop state."""
        # In most cases, we don't need to do anything
        # The test framework handles loop management
        pass


@pytest.fixture
async def loop_isolation():
    """Fixture providing event loop isolation."""
    manager = AsyncEventLoopManager()
    manager.setup_loop_isolation()
    try:
        yield manager
    finally:
        manager.restore_loop()


class DatabaseIsolationManager:
    """Manages database isolation between tests."""

    def __init__(self):
        self._transactions = []

    async def begin_transaction(self, session):
        """Begin a transaction for isolation."""
        transaction = await session.begin()
        self._transactions.append(transaction)
        return transaction

    async def rollback_all(self):
        """Rollback all transactions."""
        for transaction in reversed(self._transactions):
            try:
                await transaction.rollback()
            except Exception:
                pass  # Ignore rollback errors
        self._transactions.clear()


@pytest.fixture
async def db_isolation():
    """Fixture providing database transaction isolation."""
    manager = DatabaseIsolationManager()
    try:
        yield manager
    finally:
        await manager.rollback_all()


# Global test configuration for better isolation
def pytest_configure(config):
    """Configure pytest for better test isolation."""
    # Set asyncio mode to auto
    config.option.asyncio_mode = "auto"

    # Add markers for isolation
    config.addinivalue_line(
        "markers", "isolated: mark test as requiring full isolation"
    )
    config.addinivalue_line("markers", "shared_state: mark test as using shared state")


def pytest_runtest_setup(item):
    """Setup before each test."""
    # Clear any cached data
    from app.shared.core.rate_limit import _redis_client

    if hasattr(_redis_client, "reset"):
        _redis_client.reset()


def pytest_runtest_teardown(item):
    """Teardown after each test."""
    # Clear any remaining async tasks
    try:
        loop = asyncio.get_running_loop()
        # Cancel any remaining tasks
        tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in tasks:
            task.cancel()

        # Wait for tasks to complete cancellation
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    except RuntimeError:
        pass  # No running loop
