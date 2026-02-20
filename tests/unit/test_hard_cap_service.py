"""
Tests for BudgetHardCapService.
"""

from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.governance.domain.security.audit_log import AuditEventType
from app.shared.remediation.hard_cap_service import BudgetHardCapService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def hard_cap_service(mock_db):
    return BudgetHardCapService(mock_db)


@pytest.mark.asyncio
async def test_enforce_hard_cap_requires_explicit_approval(hard_cap_service, mock_db):
    tenant_id = uuid4()

    with patch.object(hard_cap_service, "_write_audit", new_callable=AsyncMock) as log:
        with pytest.raises(PermissionError):
            await hard_cap_service.enforce_hard_cap(tenant_id, approved=False)

    log.assert_awaited_once()
    _, kwargs = log.await_args
    assert kwargs["event_type"] == AuditEventType.BUDGET_HARD_CAP_ENFORCEMENT_BLOCKED
    mock_db.commit.assert_awaited_once()
    mock_db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_enforce_hard_cap_captures_snapshot_and_applies(hard_cap_service, mock_db):
    tenant_id = uuid4()
    snapshot = {"aws_connections": [{"id": str(uuid4()), "status": "active"}]}

    with (
        patch.object(
            hard_cap_service,
            "_capture_snapshot",
            new=AsyncMock(return_value=snapshot),
        ) as capture,
        patch.object(hard_cap_service, "_apply_enforcement", new_callable=AsyncMock) as apply,
        patch.object(hard_cap_service, "_write_audit", new_callable=AsyncMock) as log,
    ):
        result = await hard_cap_service.enforce_hard_cap(
            tenant_id,
            approved=True,
            actor_id=str(uuid4()),
            reason="budget breach",
        )

    assert result == snapshot
    capture.assert_awaited_once_with(tenant_id)
    apply.assert_awaited_once_with(tenant_id)
    log.assert_awaited_once()
    _, kwargs = log.await_args
    assert kwargs["event_type"] == AuditEventType.BUDGET_HARD_CAP_ENFORCED
    assert kwargs["details"]["snapshot"] == snapshot
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverse_hard_cap_uses_provided_snapshot(hard_cap_service, mock_db):
    tenant_id = uuid4()
    snapshot = {"aws_connections": [{"id": str(uuid4()), "status": "active"}]}

    with (
        patch.object(
            hard_cap_service,
            "_restore_from_snapshot",
            new=AsyncMock(return_value=3),
        ) as restore,
        patch.object(hard_cap_service, "_write_audit", new_callable=AsyncMock) as log,
    ):
        restored = await hard_cap_service.reverse_hard_cap(
            tenant_id,
            actor_id=str(uuid4()),
            reason="manual reactivation",
            snapshot=snapshot,
        )

    assert restored == 3
    restore.assert_awaited_once_with(tenant_id, snapshot)
    log.assert_awaited_once()
    _, kwargs = log.await_args
    assert kwargs["event_type"] == AuditEventType.BUDGET_HARD_CAP_REVERSED
    assert kwargs["details"]["restored_connections"] == 3
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverse_hard_cap_loads_latest_snapshot_when_missing(
    hard_cap_service, mock_db
):
    tenant_id = uuid4()
    snapshot = {"aws_connections": []}

    with (
        patch.object(
            hard_cap_service,
            "_load_latest_snapshot",
            new=AsyncMock(return_value=snapshot),
        ) as load,
        patch.object(
            hard_cap_service,
            "_restore_from_snapshot",
            new=AsyncMock(return_value=0),
        ) as restore,
        patch.object(hard_cap_service, "_write_audit", new_callable=AsyncMock),
    ):
        restored = await hard_cap_service.reverse_hard_cap(tenant_id)

    assert restored == 0
    load.assert_awaited_once_with(tenant_id)
    restore.assert_awaited_once_with(tenant_id, snapshot)
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reverse_hard_cap_raises_without_snapshot(hard_cap_service, mock_db):
    tenant_id = uuid4()

    with (
        patch.object(
            hard_cap_service,
            "_load_latest_snapshot",
            new=AsyncMock(return_value=None),
        ),
        patch.object(hard_cap_service, "_write_audit", new_callable=AsyncMock) as log,
    ):
        with pytest.raises(ValueError):
            await hard_cap_service.reverse_hard_cap(tenant_id)

    log.assert_not_awaited()
    mock_db.rollback.assert_awaited_once()
    mock_db.commit.assert_not_awaited()
