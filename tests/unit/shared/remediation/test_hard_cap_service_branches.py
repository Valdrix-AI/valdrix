from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.governance.domain.security.audit_log import AuditEventType
from app.shared.core.connection_queries import CONNECTION_MODEL_PAIRS
from app.shared.remediation.hard_cap_service import BudgetHardCapService


def _result_with_all(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def test_helper_coercion_and_snapshot_keys() -> None:
    tenant_id = uuid4()
    assert BudgetHardCapService._snapshot_key("aws") == "aws_connections"
    assert BudgetHardCapService._coerce_uuid(tenant_id) == tenant_id
    assert BudgetHardCapService._coerce_uuid("not-a-uuid") is None

    assert BudgetHardCapService._coerce_bool(True) is True
    assert BudgetHardCapService._coerce_bool("yes") is True
    assert BudgetHardCapService._coerce_bool("off") is False
    assert BudgetHardCapService._coerce_bool("unknown", default=True) is True

    snapshot = BudgetHardCapService._empty_snapshot()
    expected_keys = {
        BudgetHardCapService._snapshot_key(provider) for provider, _ in CONNECTION_MODEL_PAIRS
    }
    assert set(snapshot.keys()) == expected_keys
    assert all(snapshot[key] == [] for key in expected_keys)


@pytest.mark.asyncio
async def test_capture_snapshot_and_apply_enforcement_branches() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    service = BudgetHardCapService(db)

    capture_results: list[MagicMock] = []
    for provider, _model in CONNECTION_MODEL_PAIRS:
        if provider == "aws":
            capture_results.append(
                _result_with_all(
                    [
                        SimpleNamespace(id=uuid4(), status="active"),
                        SimpleNamespace(id=uuid4(), status=None),
                    ]
                )
            )
        else:
            capture_results.append(
                _result_with_all(
                    [
                        SimpleNamespace(id=uuid4(), is_active=True),
                        SimpleNamespace(id=uuid4(), is_active=False),
                    ]
                )
            )
    db.execute.side_effect = capture_results

    snapshot = await service._capture_snapshot(tenant_id)
    assert snapshot["aws_connections"][0]["status"] == "active"
    assert snapshot["aws_connections"][1]["status"] == "pending"
    assert snapshot["azure_connections"][0]["is_active"] is True
    assert db.execute.await_count == len(CONNECTION_MODEL_PAIRS)

    db.execute.reset_mock(side_effect=True)
    db.execute.side_effect = [MagicMock() for _ in CONNECTION_MODEL_PAIRS]
    await service._apply_enforcement(tenant_id)
    assert db.execute.await_count == len(CONNECTION_MODEL_PAIRS)

    rendered = [str(call.args[0]) for call in db.execute.await_args_list]
    assert any("status" in sql for sql in rendered)
    assert any("is_active" in sql for sql in rendered)


@pytest.mark.asyncio
async def test_restore_from_snapshot_skips_invalid_rows_and_restores_valid_rows() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    service = BudgetHardCapService(db)

    valid_aws_id = uuid4()
    valid_azure_id = uuid4()
    snapshot = {
        "aws_connections": [
            "not-a-dict",
            {"id": None, "status": "active"},
            {"id": "invalid", "status": "active"},
            {"id": str(valid_aws_id), "status": "active"},
        ],
        "azure_connections": [
            {"id": str(valid_azure_id), "is_active": "yes"},
        ],
    }

    restored = await service._restore_from_snapshot(tenant_id, snapshot)
    assert restored == 2
    assert db.execute.await_count == 2
    rendered = [str(call.args[0]) for call in db.execute.await_args_list]
    assert any("status" in sql for sql in rendered)
    assert any("is_active" in sql for sql in rendered)


@pytest.mark.asyncio
async def test_load_latest_snapshot_handles_missing_or_invalid_details() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    service = BudgetHardCapService(db)

    result_ok = MagicMock()
    result_ok.scalar_one_or_none.return_value = {"snapshot": {"aws_connections": []}}
    db.execute.return_value = result_ok
    assert await service._load_latest_snapshot(tenant_id) == {"aws_connections": []}

    result_missing = MagicMock()
    result_missing.scalar_one_or_none.return_value = {"snapshot": "bad"}
    db.execute.return_value = result_missing
    assert await service._load_latest_snapshot(tenant_id) is None

    result_not_dict = MagicMock()
    result_not_dict.scalar_one_or_none.return_value = "bad"
    db.execute.return_value = result_not_dict
    assert await service._load_latest_snapshot(tenant_id) is None


@pytest.mark.asyncio
async def test_write_audit_uses_audit_logger() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db = MagicMock()
    service = BudgetHardCapService(db)

    with patch("app.shared.remediation.hard_cap_service.AuditLogger") as logger_cls:
        logger_instance = logger_cls.return_value
        logger_instance.log = AsyncMock()

        await service._write_audit(
            tenant_id=tenant_id,
            event_type=AuditEventType.BUDGET_HARD_CAP_ENFORCED,
            actor_id=actor_id,
            details={"snapshot": {}},
        )

        logger_cls.assert_called_once_with(db, tenant_id)
        logger_instance.log.assert_awaited_once()


@pytest.mark.asyncio
async def test_enforce_hard_cap_rolls_back_on_capture_failure() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    service = BudgetHardCapService(db)

    with patch.object(
        service, "_capture_snapshot", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        with pytest.raises(RuntimeError):
            await service.enforce_hard_cap(tenant_id, approved=True)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reverse_hard_cap_without_callable_rollback_still_raises() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = None
    service = BudgetHardCapService(db)

    with (
        patch.object(
            service,
            "_load_latest_snapshot",
            new=AsyncMock(return_value={"aws_connections": []}),
        ),
        patch.object(
            service,
            "_restore_from_snapshot",
            new=AsyncMock(side_effect=RuntimeError("restore failed")),
        ),
    ):
        with pytest.raises(RuntimeError):
            await service.reverse_hard_cap(tenant_id)

    db.commit.assert_not_awaited()
