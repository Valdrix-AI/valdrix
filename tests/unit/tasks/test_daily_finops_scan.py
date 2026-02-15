from unittest.mock import patch, call
from app.modules.governance.domain.scheduler.cohorts import TenantCohort


def test_daily_finops_scan_exists():
    """TDD Step 1: Ensure the task exists and can be imported."""
    from app.tasks.scheduler_tasks import daily_finops_scan

    assert callable(daily_finops_scan)


@patch("app.tasks.scheduler_tasks.run_cohort_analysis")
def test_daily_finops_scan_orchestration(mock_run_cohort, caplog):
    """
    TDD Step 2: Ensure it triggers analysis for all cohorts.
    """
    from app.tasks.scheduler_tasks import daily_finops_scan

    # Execute
    daily_finops_scan()

    # Verify all cohorts are triggered independently
    assert mock_run_cohort.delay.call_count == 3
    expected_calls = [
        call(TenantCohort.HIGH_VALUE.value),
        call(TenantCohort.ACTIVE.value),
        call(TenantCohort.DORMANT.value),
    ]
    mock_run_cohort.delay.assert_has_calls(expected_calls, any_order=True)


@patch("app.tasks.scheduler_tasks.logger")
@patch("app.tasks.scheduler_tasks.run_cohort_analysis")
def test_daily_finops_scan_error_handling(mock_run_cohort, mock_logger):
    """
    TDD Step 3: Ensure one failure doesn't stop others.
    """
    from app.tasks.scheduler_tasks import daily_finops_scan

    # Make the second call fail
    mock_run_cohort.delay.side_effect = [None, Exception("Queue Full"), None]

    # Execute (should not raise exception)
    daily_finops_scan()

    # Verify we still attempted all 3
    assert mock_run_cohort.delay.call_count == 3
    mock_logger.error.assert_any_call(
        "daily_finops_scan_partial_failure",
        cohort=TenantCohort.ACTIVE.value,
        error="Queue Full",
    )
