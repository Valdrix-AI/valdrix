from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.background_job import JobType
from app.tasks.license_tasks import (
    _license_governance_sweep_logic,
    _tenant_license_governance_logic,
    run_license_governance_sweep,
    run_tenant_license_governance,
)


@pytest.fixture
def tenant_id() -> str:
    return str(uuid4())


def test_run_license_governance_sweep_wrapper() -> None:
    with patch("app.tasks.license_tasks.run_async") as mock_run_async:
        run_license_governance_sweep()
    mock_run_async.assert_called_once_with(_license_governance_sweep_logic)


def test_run_tenant_license_governance_wrapper(tenant_id: str) -> None:
    with patch("app.tasks.license_tasks.run_async") as mock_run_async:
        run_tenant_license_governance(tenant_id)
    mock_run_async.assert_called_once_with(_tenant_license_governance_logic, tenant_id)


@pytest.mark.asyncio
async def test_license_governance_sweep_dispatches_per_tenant() -> None:
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
        patch("app.tasks.license_tasks._open_db_session", return_value=_db_cm()),
        patch("app.tasks.license_tasks.BACKGROUND_JOBS_ENQUEUED") as mock_enqueued,
    ):
        await _license_governance_sweep_logic()

    assert db.execute.call_count == 3
    insert_stmt_1 = db.execute.call_args_list[1].args[0]
    assert "job_type" in str(insert_stmt_1)
    assert "deduplication_key" in str(insert_stmt_1)
    mock_enqueued.labels.assert_called_once_with(
        job_type=JobType.LICENSE_GOVERNANCE.value,
        cohort="LICENSE",
    )
    mock_enqueued.labels.return_value.inc.assert_called_once()


@pytest.mark.asyncio
async def test_license_governance_sweep_logs_and_raises() -> None:
    db = AsyncMock()
    begin_ctx = AsyncMock()
    begin_ctx.__aenter__.return_value = db
    begin_ctx.__aexit__.return_value = None
    db.begin = MagicMock(return_value=begin_ctx)
    db.execute.side_effect = RuntimeError("db down")

    @asynccontextmanager
    async def _db_cm():
        yield db

    with (
        patch("app.tasks.license_tasks._open_db_session", return_value=_db_cm()),
        patch("app.tasks.license_tasks.logger") as mock_logger,
    ):
        with pytest.raises(RuntimeError, match="db down"):
            await _license_governance_sweep_logic()

    mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_tenant_license_governance_logic_calls_service(tenant_id: str) -> None:
    db = AsyncMock()

    @asynccontextmanager
    async def _db_cm():
        yield db

    service = MagicMock()
    service.run_tenant_governance = AsyncMock()

    with (
        patch("app.tasks.license_tasks._open_db_session", return_value=_db_cm()),
        patch("app.tasks.license_tasks.LicenseGovernanceService", return_value=service),
    ):
        await _tenant_license_governance_logic(tenant_id)

    service.run_tenant_governance.assert_awaited_once()
