from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

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
async def test_archive_old_partitions_skips_unsupported_backend() -> None:
    db = AsyncMock()
    db.bind = type("Bind", (), {"dialect": type("Dialect", (), {"name": "sqlite"})()})()
    service = PartitionMaintenanceService(db)

    assert await service.archive_old_partitions(months_old=13) == 0
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_archive_old_partitions_archives_only_old_partitions() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.bind = type(
        "Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()}
    )()
    service = PartitionMaintenanceService(db)
    old_month = date.today() - relativedelta(months=14)
    recent_month = date.today() - relativedelta(months=1)
    old_partition = f"cost_records_{old_month.year}_{old_month.month:02d}"
    recent_partition = f"cost_records_{recent_month.year}_{recent_month.month:02d}"

    with (
        patch.object(
            service, "_ensure_cost_archive_table", AsyncMock(return_value=["id", "recorded_at"])
        ),
        patch.object(
            service,
            "_list_cost_record_partitions",
            AsyncMock(return_value=[old_partition, recent_partition]),
        ),
        patch.object(service, "_archive_partition", AsyncMock(return_value=5)) as archive_partition,
    ):
        archived = await service.archive_old_partitions(months_old=13)

    assert archived == 5
    archive_partition.assert_awaited_once_with(
        old_partition, shared_columns=["id", "recorded_at"]
    )
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_partition_upserts_and_drops_source_partition() -> None:
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=4)
    db.execute = AsyncMock()
    service = PartitionMaintenanceService(db)

    archived = await service._archive_partition(
        "cost_records_2024_01",
        shared_columns=["id", "tenant_id", "recorded_at"],
    )

    assert archived == 4
    assert db.scalar.await_count == 1
    assert db.execute.await_count == 3
    statements = [str(call.args[0]) for call in db.execute.await_args_list]
    assert "INSERT INTO cost_records_archive" in statements[0]
    assert "ON CONFLICT (id, recorded_at)" in statements[0]
    assert "DELETE FROM cost_records_2024_01" in statements[1]
    assert "DROP TABLE IF EXISTS cost_records_2024_01" in statements[2]
