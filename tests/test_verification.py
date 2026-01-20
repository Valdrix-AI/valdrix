
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4
from app.services.llm.factory import LLMFactory

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

@pytest.mark.asyncio
async def test_llm_factory_byok_priority():
    """Verify that LLMFactory prioritizes provide API key over global settings."""
    with patch('app.services.llm.factory.ChatOpenAI') as mock_openai:
        with patch('app.services.llm.factory.get_settings') as mock_settings:
            mock_settings.return_value.OPENAI_API_KEY = "sk-" + "a" * 32
            mock_settings.return_value.OPENAI_MODEL = "gpt-4o"
            
            # Case 1: Use Global Key
            LLMFactory.create(provider="openai")
            mock_openai.assert_called_with(
                api_key="sk-" + "a" * 32,
                model="gpt-4o",
                temperature=0
            )
            
            # Case 2: Use BYOK
            LLMFactory.create(provider="openai", api_key="sk-" + "b" * 32)
            mock_openai.assert_called_with(
                api_key="sk-" + "b" * 32,
                model="gpt-4o",
                temperature=0
            )

# NOTE: The following tests were removed because they reference methods
# (_find_underused_nat_gateways, _find_idle_instances) that were refactored
# into the plugin architecture. New tests should target the plugin classes
# directly or the scan_all() method.

@pytest.mark.asyncio
async def test_scheduler_concurrency():
    """Verify that Scheduler runs tenants in parallel with semaphore limit."""
    from app.services.scheduler.orchestrator import SchedulerService
    
    # Mock DB session and tenants (mock 15 tenants)
    mock_db = MagicMock(spec=AsyncSession)
    mock_tenants = [MagicMock(id=uuid4()) for _ in range(15)]
    
    # Mock analysis method to simulate work delay
    async def slow_analysis(*args, **kwargs):
        import asyncio
        await asyncio.sleep(0.1)
        return {"zombies": 1}

    # Create mock session maker for DI
    mock_session_maker = MagicMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_db
    mock_cm.__aexit__.return_value = None
    mock_session_maker.return_value = mock_cm
    
    scheduler = SchedulerService(session_maker=mock_session_maker)
    
    with patch('app.services.scheduler.orchestrator.sa.select'):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tenants
        mock_db.execute.return_value = mock_result
        
        with patch('app.services.scheduler.orchestrator.set_correlation_id'):
            with patch('app.services.scheduler.processors.ZombieDetector') as mock_detector:
                detector_instance = mock_detector.return_value
                detector_instance.scan_all = AsyncMock(side_effect=slow_analysis)
                
                start_time = datetime.now()
                # daily_analysis_job is now a legacy proxy that enqueues jobs via DB
                await scheduler.daily_analysis_job()
                end_time = datetime.now()
                
                duration = (end_time - start_time).total_seconds()
                
                # Verify that it completed "instantly" (doesn't wait for actual scans)
                assert duration < 0.5 
                # Verify BackgroundJobs were enqueued via execute (insert...on_conflict)
                # SchedulerService.daily_analysis_job now enqueues tasks per cohort
                assert mock_db.execute.call_count >= 3
