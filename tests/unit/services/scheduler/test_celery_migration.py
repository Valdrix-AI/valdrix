import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.modules.governance.domain.scheduler.orchestrator import SchedulerOrchestrator
from app.modules.governance.domain.scheduler.cohorts import TenantCohort


@pytest.fixture
def mock_session_maker():
    return MagicMock()


@pytest.mark.asyncio
async def test_orchestrator_dispatches_celery_tasks(mock_session_maker):
    """Verify Orchestrator calls celery_app.send_task instead of running logic."""

    orchestrator = SchedulerOrchestrator(mock_session_maker)

    with patch("app.shared.core.celery_app.celery_app.send_task") as mock_send:
        # Test Cohort Dispatch
        await orchestrator.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        mock_send.assert_called_with("scheduler.cohort_analysis", args=["high_value"])

        # Test Remediation Dispatch
        await orchestrator.auto_remediation_job()
        mock_send.assert_called_with("scheduler.remediation_sweep")

        # Test Billing Dispatch
        await orchestrator.billing_sweep_job()
        mock_send.assert_called_with("scheduler.billing_sweep")

        # Test Maintenance Dispatch
        await orchestrator.maintenance_sweep_job()
        mock_send.assert_called_with("scheduler.maintenance_sweep")

        # Test License Governance Dispatch
        await orchestrator.license_governance_sweep_job()
        mock_send.assert_called_with("license.governance_sweep")

        # Test Enforcement Reconciliation Dispatch
        await orchestrator.enforcement_reconciliation_sweep_job()
        mock_send.assert_called_with("scheduler.enforcement_reconciliation_sweep")


@pytest.mark.asyncio
async def test_scheduler_tasks_logic_execution():
    """
    Verify the TASKS themselves can run (integration-ish unit test).
    We'll mock the DB session inside the task to prevent real DB hits,
    but verify the flow.
    """
    from app.tasks.scheduler_tasks import _cohort_analysis_logic

    # Mock the session maker import in tasks
    mock_db = AsyncMock()
    mock_db.begin = MagicMock(
        return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock())
    )
    mock_db.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: []))
    )  # Empty result default

    # Patch the session maker used in tasks.
    # Note: We must patch where it is IMPORTED in scheduler_tasks
    with patch("app.tasks.scheduler_tasks.async_session_maker") as mock_maker:
        mock_maker.return_value.__aenter__.return_value = mock_db

        # Run logic directly (bypassing Celery implementation details for logic verification)
        await _cohort_analysis_logic(TenantCohort.ACTIVE)

        # Verify DB interaction
        assert mock_db.execute.called
        # Check if argument is a Select object roughly
        args, _ = mock_db.execute.call_args
        assert "Select" in str(type(args[0])) or "Select" in str(args[0])
