import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.tasks.scheduler_tasks import (
    _cohort_analysis_logic,
    _remediation_sweep_logic,
    _billing_sweep_logic,
    _maintenance_sweep_logic,
)
from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.models.tenant import Tenant


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    # AsyncSession.begin() is a synchronous method returning an async context manager
    db.begin = MagicMock()
    db_ctx = AsyncMock()
    db.begin.return_value = db_ctx
    db_ctx.__aenter__.return_value = db
    db_ctx.__aexit__.return_value = None
    return db


def _configure_session_maker(mock_maker, mock_db):
    session_ctx = AsyncMock()
    session_ctx.__aenter__.return_value = mock_db
    session_ctx.__aexit__.return_value = None
    mock_maker.return_value = session_ctx


@pytest.fixture
def mock_session_maker(mock_db):
    # Mock the context manager for async_session_maker
    maker = MagicMock()
    _configure_session_maker(maker, mock_db)
    return maker


@pytest.mark.asyncio
async def test_cohort_analysis_high_value_success(mock_db):
    """Test successful cohort analysis for high value tenants."""
    # Setup mocks
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        # Mock Tenant query result
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tenant]
        mock_db.execute.return_value = mock_result

        # Mock insert execution (return rowcount > 0 to simulate insertion)
        mock_insert_result = MagicMock()
        mock_insert_result.rowcount = 1
        # First call: Select tenants. Next calls: Insert jobs.
        mock_db.execute.side_effect = [
            mock_result,
            mock_insert_result,
            mock_insert_result,
            mock_insert_result,
            mock_insert_result,
        ]

        with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
            with patch(
                "app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"
            ) as mock_enqueued:
                await _cohort_analysis_logic(TenantCohort.HIGH_VALUE)

                # Check metrics
                assert mock_enqueued.labels.call_count == 4
                mock_runs.labels.assert_called_with(
                    job_name="cohort_high_value_enqueue", status="success"
                )


@pytest.mark.asyncio
async def test_cohort_analysis_deadlock_retry(mock_db):
    """Test deadlock retry logic."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.id = "uuid-1"
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_tenant]

        mock_db.execute.side_effect = [
            Exception("Deadlock detected"),  # Attempt 1 fail
            mock_result,  # Attempt 2 select success
            MagicMock(rowcount=1),  # Attempt 2 insert 1
            MagicMock(rowcount=1),  # Attempt 2 insert 2
            MagicMock(rowcount=1),  # Attempt 2 insert 3
            MagicMock(rowcount=1),  # Attempt 2 insert 4
        ]

        with patch(
            "app.tasks.scheduler_tasks.SCHEDULER_DEADLOCK_DETECTED"
        ) as mock_deadlock:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await _cohort_analysis_logic(TenantCohort.ACTIVE)
                mock_deadlock.labels.return_value.inc.assert_called_once()
                mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_remediation_sweep_success(mock_db):
    """Test remediation sweep enqueues jobs."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        mock_conn = MagicMock()
        mock_conn.id = "conn-1"
        mock_conn.tenant_id = "tenant-1"
        mock_conn.region = "us-east-1"

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_result.scalars.return_value.all.return_value = [mock_conn]
        mock_db.execute.return_value = mock_result

        with patch(
            "app.modules.governance.domain.scheduler.orchestrator.SchedulerOrchestrator.is_low_carbon_window",
            new_callable=AsyncMock,
        ) as mock_green:
            mock_green.return_value = True
            with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
                await _remediation_sweep_logic()
                mock_runs.labels.assert_called_with(
                    job_name="weekly_remediation_sweep", status="success"
                )


@pytest.mark.asyncio
async def test_billing_sweep_success(mock_db):
    """Test billing sweep success."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        mock_sub = MagicMock()
        mock_sub.id = "sub-1"
        mock_sub.tenant_id = "tenant-1"

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_result.scalars.return_value.all.return_value = [mock_sub]
        mock_db.execute.return_value = mock_result

        with patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs:
            await _billing_sweep_logic()
            mock_runs.labels.assert_called_with(
                job_name="daily_billing_sweep", status="success"
            )


@pytest.mark.asyncio
async def test_maintenance_sweep_success(mock_db):
    """Test maintenance sweep success path."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        with (
            patch(
                "app.tasks.scheduler_tasks.CostPersistenceService"
            ) as mock_persist_cls,
            patch("app.tasks.scheduler_tasks.CostAggregator") as mock_agg_cls,
            patch(
                "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
                new_callable=AsyncMock,
            ) as mock_auto_activate,
        ):
            mock_persist = MagicMock()
            mock_persist.finalize_batch = AsyncMock(
                return_value={"records_finalized": 100}
            )
            mock_persist_cls.return_value = mock_persist

            mock_agg = MagicMock()
            mock_agg.refresh_materialized_view = AsyncMock()
            mock_agg_cls.return_value = mock_agg
            mock_auto_activate.return_value = {
                "status": "no_update",
                "active_factor_set_id": "seeded",
            }

            await _maintenance_sweep_logic()
            mock_persist.finalize_batch.assert_called_with(days_ago=2)
            mock_agg.refresh_materialized_view.assert_called_with(mock_db)
            mock_auto_activate.assert_awaited_once()


@pytest.mark.asyncio
async def test_maintenance_archive_logging(mock_db):
    """Test that maintenance archive failures are logged correctly."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        # Precise mock to only fail the archive statement
        def execute_side_effect(stmt, *args, **kwargs):
            if hasattr(stmt, "text") and "archive_old_cost_partitions" in stmt.text:
                raise Exception("Archive Failure")
            return MagicMock()

        mock_db.execute.side_effect = execute_side_effect

        async def _fake_finalize_batch(self, days_ago):
            return {"records_finalized": 0}

        async def _fake_refresh_materialized_view(self, db):
            return None

        with patch("app.tasks.scheduler_tasks.logger") as mock_logger:
            # Use explicit async stubs instead of AsyncMock to avoid coroutine leak warnings
            with (
                patch(
                    "app.tasks.scheduler_tasks.CostPersistenceService.finalize_batch",
                    new=_fake_finalize_batch,
                ),
                patch(
                    "app.tasks.scheduler_tasks.CostAggregator.refresh_materialized_view",
                    new=_fake_refresh_materialized_view,
                ),
            ):
                await _maintenance_sweep_logic()
                mock_logger.error.assert_called_with(
                    "maintenance_archive_failed", error="Archive Failure"
                )


@pytest.mark.asyncio
async def test_maintenance_carbon_factor_refresh_failure_is_logged(mock_db):
    """Carbon factor refresh failures should be warning-only (best-effort)."""
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        _configure_session_maker(mock_maker, mock_db)

        async def _fake_finalize_batch(self, days_ago):
            return {"records_finalized": 0}

        async def _fake_refresh_materialized_view(self, db):
            return None

        with patch("app.tasks.scheduler_tasks.logger") as mock_logger:
            with (
                patch(
                    "app.tasks.scheduler_tasks.CostPersistenceService.finalize_batch",
                    new=_fake_finalize_batch,
                ),
                patch(
                    "app.tasks.scheduler_tasks.CostAggregator.refresh_materialized_view",
                    new=_fake_refresh_materialized_view,
                ),
                patch(
                    "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
                    new_callable=AsyncMock,
                ) as mock_auto_activate,
            ):
                mock_auto_activate.side_effect = RuntimeError("factor refresh failed")
                await _maintenance_sweep_logic()
                mock_logger.warning.assert_any_call(
                    "maintenance_carbon_factor_refresh_failed",
                    error="factor refresh failed",
                )
