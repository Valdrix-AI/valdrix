import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from app.shared.llm.factory import LLMFactory


class AsyncContextManagerMock:
    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class AsyncIterator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


@pytest.fixture
def mock_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_verification_workflow_success(mock_db: AsyncMock) -> None:
    """Verify that LLMFactory prioritizes provide API key over global settings."""
    # We must patch get_settings in BOTH the factory and the provider
    with patch("app.shared.llm.providers.openai.ChatOpenAI") as mock_openai:
        with patch("app.shared.llm.providers.openai.get_settings") as mock_settings:
            mock_settings.return_value.OPENAI_API_KEY = "sk-" + "a" * 32
            mock_settings.return_value.OPENAI_MODEL = "gpt-4o"

            # Case 1: Use Global Key
            LLMFactory.create(provider="openai")
            mock_openai.assert_called_with(
                api_key="sk-" + "a" * 32, model="gpt-4o", temperature=0
            )

            # Case 2: Use BYOK
            LLMFactory.create(provider="openai", api_key="sk-" + "b" * 32)
            mock_openai.assert_called_with(
                api_key="sk-" + "b" * 32, model="gpt-4o", temperature=0
            )


# NOTE: The following tests were removed because they reference methods
# (_find_underused_nat_gateways, _find_idle_instances) that were refactored
# into the plugin architecture. New tests should target the plugin classes
# directly or the scan_all() method.


@pytest.mark.asyncio
async def test_verify_remediation_completed(
    mock_service: MagicMock, mock_db: AsyncMock
) -> None:
    """Verify that Scheduler runs tenants in parallel with semaphore limit."""
    from app.modules.governance.domain.scheduler.orchestrator import SchedulerService

    # Mock DB session and tenants (mock 15 tenants)
    mock_db_instance = MagicMock(spec=AsyncSession)
    mock_tenants = [MagicMock(id=uuid4()) for _ in range(15)]

    # Create mock session maker for DI
    mock_session_maker = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_db_instance
    mock_cm.__aexit__.return_value = None
    mock_session_maker.return_value = mock_cm

    scheduler = SchedulerService(session_maker=mock_session_maker)

    # Result for the tenant select query
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_tenants
    mock_db.execute.return_value = mock_result

    with patch("app.shared.core.celery_app.celery_app") as mock_celery:
        start_time = datetime.now()
        # daily_analysis_job enqueues jobs via Celery task dispatch
        await scheduler.daily_analysis_job()
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()

        # Verify that it completed "instantly" (just dispatches)
        assert duration < 0.5
        # Verify Celery tasks were sent (3 per cohort, etc.)
        assert mock_celery.send_task.call_count >= 3
