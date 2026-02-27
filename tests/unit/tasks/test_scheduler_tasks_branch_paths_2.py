from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import pytest

from app.modules.governance.domain.scheduler.cohorts import TenantCohort
from app.tasks import scheduler_tasks as st


@asynccontextmanager
async def _db_cm(db: AsyncMock):
    yield db


def _begin_cm(db: AsyncMock) -> AsyncMock:
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__.return_value = db
    begin_ctx.__aexit__.return_value = None
    return begin_ctx


def _configure_sync_begin(db: AsyncMock) -> None:
    db.begin = MagicMock(return_value=_begin_cm(db))


def _configure_awaitable_begin(db: AsyncMock) -> None:
    begin_ctx = _begin_cm(db)

    async def _begin() -> AsyncMock:
        return begin_ctx

    db.begin = MagicMock(side_effect=_begin)


def _scalars_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def _rowcount_result(count: int) -> MagicMock:
    result = MagicMock()
    result.rowcount = count
    return result


class _TimeoutRaiser:
    async def __aenter__(self) -> None:
        raise asyncio.TimeoutError("db session timeout")

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_open_db_session_timeout_logs_and_raises() -> None:
    cm = _begin_cm(AsyncMock())
    with (
        patch("app.tasks.scheduler_tasks.async_session_maker", return_value=cm),
        patch("app.tasks.scheduler_tasks.asyncio.timeout", return_value=_TimeoutRaiser()),
        patch("app.tasks.scheduler_tasks.logger") as mock_logger,
    ):
        with pytest.raises(asyncio.TimeoutError):
            async with st._open_db_session():
                pass

    mock_logger.error.assert_called_once()


def test_run_async_callable_and_invalid_type_paths() -> None:
    async def _fn(value: int) -> int:
        return value + 1

    assert st.run_async(_fn, 41) == 42
    with pytest.raises(TypeError):
        st.run_async(12345)


def test_run_cohort_analysis_accepts_enum_instance_and_value_fallback() -> None:
    with patch("app.tasks.scheduler_tasks.run_async") as mock_run_async:
        st.run_cohort_analysis(TenantCohort.ACTIVE)
        st.run_cohort_analysis("dormant")

    assert mock_run_async.call_count == 2
    assert mock_run_async.call_args_list[0].args[1] == TenantCohort.ACTIVE
    assert mock_run_async.call_args_list[1].args[1] == TenantCohort.DORMANT


@pytest.mark.asyncio
async def test_cohort_analysis_dormant_branch_skips_optional_jobs_and_zero_enqueues() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)

    tenant = SimpleNamespace(id=uuid4(), plan="starter")
    db.execute.side_effect = [
        _scalars_result([tenant]),
        _rowcount_result(0),
    ]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.datetime") as mock_datetime,
        patch("app.shared.core.pricing.is_feature_enabled", side_effect=[False, False, False]),
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_datetime.now.return_value = datetime(2026, 2, 1, 11, 59, tzinfo=timezone.utc)
        await st._cohort_analysis_logic(TenantCohort.DORMANT)

    mock_enqueued.labels.assert_not_called()
    # one select + one insert (only zombie scan job)
    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_cohort_analysis_deadlock_final_retry_records_failure() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    db.execute = AsyncMock(side_effect=[Exception("deadlock"), Exception("deadlock"), Exception("deadlock")])

    with (
        patch(
            "app.tasks.scheduler_tasks._open_db_session",
            side_effect=lambda: _db_cm(db),
        ),
        patch("app.tasks.scheduler_tasks.SCHEDULER_DEADLOCK_DETECTED") as mock_deadlock,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await st._cohort_analysis_logic(TenantCohort.HIGH_VALUE)

    assert mock_deadlock.labels.return_value.inc.call_count == 3
    assert mock_sleep.await_count == 2
    mock_runs.labels.assert_any_call(job_name="cohort_high_value_enqueue", status="failure")


@pytest.mark.asyncio
async def test_cohort_analysis_chunk_loop_handles_missing_rowcount_first_chunk() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)

    tenants = [SimpleNamespace(id=uuid4(), plan="starter") for _ in range(501)]
    db.execute.side_effect = [
        _scalars_result(tenants),
        object(),  # first chunk result has no rowcount
        _rowcount_result(0),
    ]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.datetime") as mock_datetime,
        patch(
            "app.shared.core.pricing.is_feature_enabled",
            side_effect=[False] * (len(tenants) * 3),
        ),
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_datetime.now.return_value = datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc)
        await st._cohort_analysis_logic(TenantCohort.DORMANT)

    assert db.execute.call_count == 3


@pytest.mark.asyncio
async def test_remediation_sweep_skips_unknown_provider_connections() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    db.execute = AsyncMock()

    conn = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch(
            "app.tasks.scheduler_tasks._load_active_remediation_connections",
            new=AsyncMock(return_value=[conn]),
        ),
        patch("app.tasks.scheduler_tasks.resolve_provider_from_connection", return_value="mystery"),
        patch("app.tasks.scheduler_tasks.normalize_provider", return_value=None),
        patch("app.tasks.scheduler_tasks.SchedulerOrchestrator"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
        patch("app.tasks.scheduler_tasks.logger") as mock_logger,
    ):
        await st._remediation_sweep_logic()

    db.execute.assert_not_called()
    mock_logger.warning.assert_any_call(
        "remediation_sweep_skipping_unknown_provider",
        provider="mystery",
        connection_id=str(conn.id),
        tenant_id=str(conn.tenant_id),
    )


@pytest.mark.asyncio
async def test_remediation_sweep_retries_once_then_succeeds() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)

    with (
        patch(
            "app.tasks.scheduler_tasks._open_db_session",
            side_effect=lambda: _db_cm(db),
        ),
        patch(
            "app.tasks.scheduler_tasks._load_active_remediation_connections",
            new=AsyncMock(side_effect=[RuntimeError("load failed"), []]),
        ),
        patch("app.tasks.scheduler_tasks.SchedulerOrchestrator"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await st._remediation_sweep_logic()

    mock_sleep.assert_awaited_once()
    mock_runs.labels.assert_any_call(job_name="weekly_remediation_sweep", status="success")


@pytest.mark.asyncio
async def test_remediation_sweep_final_failure_records_metric() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)

    with (
        patch(
            "app.tasks.scheduler_tasks._open_db_session",
            side_effect=lambda: _db_cm(db),
        ),
        patch(
            "app.tasks.scheduler_tasks._load_active_remediation_connections",
            new=AsyncMock(side_effect=RuntimeError("persistent failure")),
        ),
        patch("app.tasks.scheduler_tasks.SchedulerOrchestrator"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        await st._remediation_sweep_logic()

    assert mock_sleep.await_count == 2
    mock_runs.labels.assert_any_call(job_name="weekly_remediation_sweep", status="failure")


@pytest.mark.asyncio
async def test_remediation_sweep_chunk_loop_handles_missing_rowcount_first_chunk() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    db.execute.side_effect = [object(), _rowcount_result(0)]

    connections = [
        SimpleNamespace(id=uuid4(), tenant_id=uuid4(), provider="aws", region="global")
        for _ in range(501)
    ]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch(
            "app.tasks.scheduler_tasks._load_active_remediation_connections",
            new=AsyncMock(return_value=connections),
        ),
        patch("app.tasks.scheduler_tasks.resolve_provider_from_connection", return_value="aws"),
        patch("app.tasks.scheduler_tasks.normalize_provider", return_value="aws"),
        patch("app.tasks.scheduler_tasks.resolve_connection_region", return_value="global"),
        patch("app.tasks.scheduler_tasks.SchedulerOrchestrator"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        await st._remediation_sweep_logic()

    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_billing_sweep_handles_zero_then_positive_rowcount() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)

    sub1 = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    sub2 = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    db.execute.side_effect = [
        _scalars_result([sub1, sub2]),
        _rowcount_result(0),
        _rowcount_result(1),
    ]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        await st._billing_sweep_logic()

    mock_enqueued.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_acceptance_sweep_begin_ctx_awaitable_no_tenants_returns_early() -> None:
    db = AsyncMock()
    _configure_awaitable_begin(db)
    db.execute.return_value = _scalars_result([])

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.logger") as mock_logger,
    ):
        await st._acceptance_sweep_logic()

    mock_logger.info.assert_any_call("acceptance_sweep_no_tenants")


@pytest.mark.asyncio
async def test_acceptance_sweep_quarterly_payload_flags_and_rowcount_zero_branch() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    tenants = [SimpleNamespace(id=uuid4()), SimpleNamespace(id=uuid4())]
    db.execute.side_effect = [
        _scalars_result(tenants),
        _rowcount_result(0),
        _rowcount_result(1),
    ]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.datetime") as mock_datetime,
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_datetime.now.return_value = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        await st._acceptance_sweep_logic()

    insert_stmt = db.execute.call_args_list[1].args[0]
    compiled = insert_stmt.compile()
    payload = compiled.params.get("payload")
    assert payload == {
        "capture_close_package": True,
        "capture_quarterly_report": True,
    }
    mock_enqueued.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_acceptance_sweep_close_only_payload_path() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    tenant = SimpleNamespace(id=uuid4())
    db.execute.side_effect = [_scalars_result([tenant]), _rowcount_result(1)]

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.datetime") as mock_datetime,
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_datetime.now.return_value = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
        await st._acceptance_sweep_logic()

    insert_stmt = db.execute.call_args_list[1].args[0]
    payload = insert_stmt.compile().params.get("payload")
    assert payload == {"capture_close_package": True}


@pytest.mark.asyncio
async def test_acceptance_sweep_retries_then_succeeds() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    tenant = SimpleNamespace(id=uuid4())
    db.execute.side_effect = [
        RuntimeError("temporary failure"),
        _scalars_result([tenant]),
        _rowcount_result(1),
    ]

    with (
        patch(
            "app.tasks.scheduler_tasks._open_db_session",
            side_effect=lambda: _db_cm(db),
        ),
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        await st._acceptance_sweep_logic()

    mock_sleep.assert_awaited_once()
    mock_runs.labels.assert_any_call(job_name="daily_acceptance_sweep", status="success")


@pytest.mark.asyncio
async def test_acceptance_sweep_final_failure_records_metric() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    db.execute = AsyncMock(side_effect=RuntimeError("persistent failure"))

    with (
        patch(
            "app.tasks.scheduler_tasks._open_db_session",
            side_effect=lambda: _db_cm(db),
        ),
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        await st._acceptance_sweep_logic()

    assert mock_sleep.await_count == 2
    mock_runs.labels.assert_any_call(job_name="daily_acceptance_sweep", status="failure")


@pytest.mark.asyncio
async def test_maintenance_sweep_realized_savings_success_with_sync_carbon_commit() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.rollback = AsyncMock(return_value=None)

    commit_async = AsyncMock(return_value=None)
    commit_calls = {"count": 0}

    def _commit_side_effect() -> object:
        commit_calls["count"] += 1
        if commit_calls["count"] == 1:
            return None  # carbon factor refresh path exercises non-awaitable branch
        return commit_async()

    db.commit = MagicMock(side_effect=_commit_side_effect)

    req1 = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    req2 = SimpleNamespace(id=uuid4(), tenant_id=uuid4())
    db.execute.return_value = _scalars_result([req1, req2])

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.CostPersistenceService") as mock_persistence_cls,
        patch("app.tasks.scheduler_tasks.CostAggregator") as mock_aggregator_cls,
        patch(
            "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
            new=AsyncMock(return_value={"status": "activated", "active_factor_set_id": "a1", "candidate_factor_set_id": "c1"}),
        ),
        patch("app.modules.reporting.domain.realized_savings.RealizedSavingsService") as mock_realized_cls,
        patch("app.shared.core.maintenance.PartitionMaintenanceService") as mock_maintenance_cls,
    ):
        mock_persistence_cls.return_value.finalize_batch = AsyncMock(return_value={"records_finalized": 1})
        mock_aggregator_cls.return_value.refresh_materialized_view = AsyncMock(return_value=None)
        mock_realized_service = MagicMock()
        mock_realized_service.compute_for_request = AsyncMock(side_effect=[object(), None])
        mock_realized_cls.return_value = mock_realized_service
        mock_maintenance = MagicMock()
        mock_maintenance.create_future_partitions = AsyncMock(return_value=1)
        mock_maintenance.archive_old_partitions = AsyncMock(return_value=2)
        mock_maintenance_cls.return_value = mock_maintenance

        await st._maintenance_sweep_logic()

    assert commit_calls["count"] >= 3
    mock_realized_service.compute_for_request.assert_has_awaits(
        [
            call(tenant_id=req1.tenant_id, request=req1, require_final=True),
            call(tenant_id=req2.tenant_id, request=req2, require_final=True),
        ]
    )


@pytest.mark.asyncio
async def test_maintenance_sweep_realized_savings_query_failure_and_sync_rollback() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("realized query failed"))
    db.commit = AsyncMock(return_value=None)
    db.rollback = MagicMock(return_value=None)  # carbon-factor failure path non-awaitable rollback

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.CostPersistenceService") as mock_persistence_cls,
        patch("app.tasks.scheduler_tasks.CostAggregator") as mock_aggregator_cls,
        patch(
            "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
            new=AsyncMock(side_effect=RuntimeError("factor refresh failed")),
        ),
        patch("app.shared.core.maintenance.PartitionMaintenanceService") as mock_maintenance_cls,
        patch("app.tasks.scheduler_tasks.logger") as mock_logger,
    ):
        mock_persistence_cls.return_value.finalize_batch = AsyncMock(return_value={"records_finalized": 0})
        mock_aggregator_cls.return_value.refresh_materialized_view = AsyncMock(return_value=None)
        mock_maintenance = MagicMock()
        mock_maintenance.create_future_partitions = AsyncMock(return_value=0)
        mock_maintenance.archive_old_partitions = AsyncMock(return_value=0)
        mock_maintenance_cls.return_value = mock_maintenance

        await st._maintenance_sweep_logic()

    db.rollback.assert_called()
    mock_logger.warning.assert_any_call("maintenance_carbon_factor_refresh_failed", error="factor refresh failed")
    mock_logger.warning.assert_any_call("maintenance_realized_savings_compute_failed", error="realized query failed")


@pytest.mark.asyncio
async def test_enforcement_reconciliation_sweep_begin_ctx_awaitable_success() -> None:
    db = AsyncMock()
    _configure_awaitable_begin(db)
    db.execute.return_value = _scalars_result([])

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.get_settings") as mock_settings,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_settings.return_value = SimpleNamespace(ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED=True)
        await st._enforcement_reconciliation_sweep_logic()

    mock_runs.labels.assert_any_call(
        job_name="hourly_enforcement_reconciliation_sweep", status="success"
    )


@pytest.mark.asyncio
async def test_enforcement_reconciliation_sweep_retries_and_records_failure() -> None:
    db = AsyncMock()
    _configure_sync_begin(db)
    db.execute = AsyncMock(side_effect=RuntimeError("queue failed"))

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm(db)),
        patch("app.tasks.scheduler_tasks.get_settings") as mock_settings,
        patch("app.tasks.scheduler_tasks.asyncio.sleep", new=AsyncMock()) as mock_sleep,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS") as mock_runs,
        patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
    ):
        mock_settings.return_value = SimpleNamespace(ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED=True)
        await st._enforcement_reconciliation_sweep_logic()

    assert mock_sleep.await_count == 2
    mock_runs.labels.assert_any_call(
        job_name="hourly_enforcement_reconciliation_sweep", status="failure"
    )


def test_daily_finops_scan_logs_partial_failure_and_completion() -> None:
    task = MagicMock()
    task.delay.side_effect = [None, RuntimeError("dispatch failed"), None]

    with patch("app.tasks.scheduler_tasks.run_cohort_analysis", task), patch(
        "app.tasks.scheduler_tasks.logger"
    ) as mock_logger:
        st.daily_finops_scan()

    assert task.delay.call_count == len(list(TenantCohort))
    mock_logger.error.assert_any_call(
        "daily_finops_scan_partial_failure",
        cohort=TenantCohort.ACTIVE.value,
        error="dispatch failed",
    )
    mock_logger.info.assert_any_call(
        "daily_finops_scan_completed",
        duration_seconds=mock_logger.info.call_args_list[-1].kwargs["duration_seconds"],
        successful=2,
        failed=1,
    )
