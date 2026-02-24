from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.background_job import JobType
from app.tasks.scheduler_tasks import (
    _enforcement_reconciliation_sweep_logic,
    run_enforcement_reconciliation_sweep,
)


def test_run_enforcement_reconciliation_sweep_wrapper() -> None:
    with patch("app.tasks.scheduler_tasks.run_async") as mock_run_async:
        run_enforcement_reconciliation_sweep()
    mock_run_async.assert_called_once_with(_enforcement_reconciliation_sweep_logic)


@pytest.mark.asyncio
async def test_enforcement_reconciliation_sweep_dispatches_per_tenant() -> None:
    tenant_ids = [uuid4(), uuid4()]
    db = AsyncMock()
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__.return_value = db
    begin_ctx.__aexit__.return_value = None
    db.begin = MagicMock(return_value=begin_ctx)

    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = tenant_ids
    first_insert = MagicMock()
    first_insert.rowcount = 1
    second_insert = MagicMock()
    second_insert.rowcount = 0
    db.execute.side_effect = [select_result, first_insert, second_insert]

    @asynccontextmanager
    async def _db_cm():
        yield db

    with (
        patch("app.tasks.scheduler_tasks._open_db_session", return_value=_db_cm()),
        patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued,
        patch("app.tasks.scheduler_tasks.get_settings") as mock_settings,
    ):
        mock_settings.return_value = SimpleNamespace(
            ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED=True,
        )
        await _enforcement_reconciliation_sweep_logic()

    assert db.execute.call_count == 3
    insert_stmt = db.execute.call_args_list[1].args[0]
    compiled = insert_stmt.compile()
    assert compiled.params.get("job_type") == JobType.ENFORCEMENT_RECONCILIATION.value
    assert "deduplication_key" in str(insert_stmt)
    mock_enqueued.labels.assert_called_once_with(
        job_type=JobType.ENFORCEMENT_RECONCILIATION.value,
        cohort="ENFORCEMENT",
    )
    mock_enqueued.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_enforcement_reconciliation_sweep_skips_when_disabled() -> None:
    with (
        patch("app.tasks.scheduler_tasks.get_settings") as mock_settings,
        patch("app.tasks.scheduler_tasks._open_db_session") as mock_open_db,
        patch("app.tasks.scheduler_tasks.logger") as mock_logger,
    ):
        mock_settings.return_value = SimpleNamespace(
            ENFORCEMENT_RECONCILIATION_SWEEP_ENABLED=False,
        )
        await _enforcement_reconciliation_sweep_logic()

    mock_open_db.assert_not_called()
    mock_logger.info.assert_called_with("enforcement_reconciliation_sweep_disabled")
