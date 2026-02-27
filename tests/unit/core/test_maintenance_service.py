from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.shared.core.maintenance import PartitionMaintenanceService


def _db(*, exists_sequence: list[bool], execute_side_effect=None):
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=exists_sequence)
    db.execute = AsyncMock(side_effect=execute_side_effect)
    return db


@pytest.mark.asyncio
async def test_create_future_partitions_skips_existing_partitions() -> None:
    db = _db(exists_sequence=[True])
    service = PartitionMaintenanceService(db)

    with patch.object(PartitionMaintenanceService, "SUPPORTED_TABLES", ("cost_records",)):
        created = await service.create_future_partitions(months_ahead=0)

    assert created == 0
    # advisory lock + existence check path only (no create/alter SQL)
    assert db.execute.await_count == 1
    db.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_future_partitions_creates_partition_and_enables_rls() -> None:
    db = _db(exists_sequence=[False])
    service = PartitionMaintenanceService(db)

    with (
        patch.object(PartitionMaintenanceService, "SUPPORTED_TABLES", ("audit_logs",)),
        patch("app.shared.core.maintenance.logger.info") as logger_info,
    ):
        created = await service.create_future_partitions(months_ahead=0)

    assert created == 1
    # advisory lock + create + enable rls + force rls
    assert db.execute.await_count == 4
    logger_info.assert_called_once()


@pytest.mark.asyncio
async def test_create_future_partitions_logs_and_continues_on_create_error() -> None:
    calls = {"n": 0}

    async def _execute_side_effect(*args, **kwargs):
        del kwargs
        calls["n"] += 1
        # 1 advisory lock, 2 create table -> fail
        if calls["n"] == 2:
            raise RuntimeError("ddl failed")
        return None

    db = _db(exists_sequence=[False], execute_side_effect=_execute_side_effect)
    service = PartitionMaintenanceService(db)

    with (
        patch.object(PartitionMaintenanceService, "SUPPORTED_TABLES", ("cost_records",)),
        patch("app.shared.core.maintenance.logger.error") as logger_error,
    ):
        created = await service.create_future_partitions(months_ahead=0)

    assert created == 0
    logger_error.assert_called_once()


@pytest.mark.asyncio
async def test_archive_old_partitions_success_and_failure_paths() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    service = PartitionMaintenanceService(db)

    assert await service.archive_old_partitions(months_old=13) == 1

    db.execute = AsyncMock(side_effect=RuntimeError("missing function"))
    with patch("app.shared.core.maintenance.logger.warning") as warning:
        assert await service.archive_old_partitions(months_old=13) == 0
    warning.assert_called_once()

