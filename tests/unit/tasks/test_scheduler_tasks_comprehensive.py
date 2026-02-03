import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.tasks.scheduler_tasks import (
    _cohort_analysis_logic,
    _remediation_sweep_logic,
    _billing_sweep_logic,
    _maintenance_sweep_logic
)
from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.models.tenant import Tenant

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # AsyncSession.begin() is a synchronous method returning an async context manager
    db.begin = MagicMock()
    db_ctx = AsyncMock() 
    db.begin.return_value = db_ctx
    db_ctx.__aenter__.return_value = db
    db_ctx.__aexit__.return_value = None
    return db

@pytest.fixture
def mock_session_maker(mock_db):
    # Mock the context manager for async_session_maker
    maker = MagicMock()
    maker.return_value.__aenter__.return_value = mock_db
    maker.return_value.__aexit__.return_value = None
    return maker

@pytest.mark.asyncio
async def test_cohort_analysis_high_value_success(mock_db):
    """Test successful cohort analysis for high value tenants."""
    # Setup mocks
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db
        
        # Mock Tenant query result
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tenant]
        mock_db.execute.return_value = mock_result
        
        # Mock insert execution (return rowcount > 0 to simulate insertion)
        mock_insert_result = MagicMock()
        mock_insert_result.rowcount = 1
        # The subsequent executes are for inserting jobs
        # We need check how many times execute is called.
        # First call: Select tenants. 
        # Next 3 calls: Insert jobs (3 types per tenant).
        mock_db.execute.side_effect = [mock_result, mock_insert_result, mock_insert_result, mock_insert_result]

        with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
            with patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued:
                await _cohort_analysis_logic(TenantCohort.HIGH_VALUE)
                
                # Check metrics
                assert mock_enqueued.labels.call_count == 3
                mock_runs.labels.assert_called_with(job_name="cohort_high_value_enqueue", status="success")
                mock_runs.labels.return_value.inc.assert_called()

@pytest.mark.asyncio
async def test_cohort_analysis_deadlock_retry(mock_db):
    """Test deadlock retry logic."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db
        
        # First call raises deadlock exception
        # Second call returns success
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tenant]
        
        mock_db.execute.side_effect = [
            Exception("Deadlock detected"), # Attempt 1 fail
            mock_result, # Attempt 2 select success
            MagicMock(rowcount=1), # Attempt 2 insert 1
            MagicMock(rowcount=1), # Attempt 2 insert 2
            MagicMock(rowcount=1)  # Attempt 2 insert 3
        ]
        
        with patch("app.tasks.scheduler_tasks.SCHEDULER_DEADLOCK_DETECTED") as mock_deadlock:
            # We mock sleep to speed up test
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await _cohort_analysis_logic(TenantCohort.ACTIVE)
                
                # Assert deadlock metric incremented
                mock_deadlock.labels.assert_called_with(cohort="active")
                mock_deadlock.labels.return_value.inc.assert_called_once()
                # Assert sleep called (backoff)
                mock_sleep.assert_called_once()

@pytest.mark.asyncio
async def test_remediation_sweep_success(mock_db):
    """Test remediation sweep enqueues jobs for connections."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db
        
        # Mock Connection query
        mock_conn = MagicMock()
        mock_conn.id = "conn-1"
        mock_conn.tenant_id = "tenant-1"
        mock_conn.region = "us-east-1"
        
        mock_result = MagicMock()
        mock_result.rowcount = 1 # For insert result
        mock_result.scalars.return_value.all.return_value = [mock_conn]
        mock_db.execute.return_value = mock_result
        
        with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
            await _remediation_sweep_logic()
            
            mock_runs.labels.assert_called_with(job_name="weekly_remediation_sweep", status="success")

@pytest.mark.asyncio
async def test_billing_sweep_success(mock_db):
    """Test billing sweep enqueues jobs for due subscriptions."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db
        
        mock_sub = MagicMock()
        mock_sub.id = "sub-1"
        mock_sub.tenant_id = "tenant-1"
        
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_result.scalars.return_value.all.return_value = [mock_sub]
        mock_db.execute.return_value = mock_result
        
        with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
            await _billing_sweep_logic()
            
            mock_runs.labels.assert_called_with(job_name="daily_billing_sweep", status="success")

@pytest.mark.asyncio
async def test_maintenance_sweep_success(mock_db):
    """Test maintenance sweep calls aggregators."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db
        
        with patch("app.modules.reporting.domain.persistence.CostPersistenceService") as mock_persist_cls:
            mock_persist = MagicMock()
            mock_persist_cls.return_value = mock_persist
            mock_persist.finalize_batch = AsyncMock(return_value={"records_finalized": 100})
            
            with patch("app.modules.reporting.domain.aggregator.CostAggregator.refresh_materialized_view", new_callable=AsyncMock) as mock_refresh:
                await _maintenance_sweep_logic()
                
                mock_persist.finalize_batch.assert_called_with(days_ago=2)
                mock_refresh.assert_called_with(mock_db)
                mock_db.execute.assert_called() # Archive call
