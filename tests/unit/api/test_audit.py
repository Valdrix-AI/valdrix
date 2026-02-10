import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from uuid import uuid4
from datetime import datetime, timezone
from app.modules.audit import (
    get_audit_logs, 
    get_audit_log_detail, 
    export_audit_logs, 
    request_data_erasure,
    get_event_types
)
from app.shared.core.auth import CurrentUser
from app.modules.governance.domain.security.audit_log import AuditLog

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def admin_user():
    return CurrentUser(id=uuid4(), email="admin@test.com", tenant_id=uuid4(), role="admin")

@pytest.fixture
def owner_user():
    return CurrentUser(id=uuid4(), email="owner@test.com", tenant_id=uuid4(), role="owner")

@pytest.mark.asyncio
async def test_get_audit_logs_success(mock_db, admin_user):
    mock_log = MagicMock(spec=AuditLog)
    mock_log.id = uuid4()
    mock_log.event_type = "login"
    mock_log.event_timestamp = datetime.now(timezone.utc)
    mock_log.actor_email = "test@test.com"
    mock_log.resource_type = "user"
    mock_log.resource_id = str(uuid4())
    mock_log.success = True
    mock_log.correlation_id = "corr-1"
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_log]
    mock_db.execute.return_value = mock_res
    
    # Coverage for event_type filter
    logs = await get_audit_logs(
        admin_user, 
        mock_db, 
        limit=50,
        offset=0,
        event_type="login",
        sort_by="event_timestamp", 
        order="desc"
    )
    assert len(logs) == 1
    assert logs[0].event_type == "login"

@pytest.mark.asyncio
async def test_get_audit_logs_error(mock_db, admin_user):
    mock_db.execute.side_effect = Exception("DB error")
    with pytest.raises(HTTPException) as exc:
        await get_audit_logs(admin_user, mock_db)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_get_audit_log_detail_success(mock_db, admin_user):
    mock_log = MagicMock(spec=AuditLog)
    mock_log.id = uuid4()
    mock_log.event_type = "test"
    mock_log.event_timestamp = datetime.now(timezone.utc)
    mock_log.actor_id = uuid4()
    mock_log.actor_email = "a@b.com"
    mock_log.actor_ip = "1.1.1.1"
    mock_log.correlation_id = "c1"
    mock_log.request_method = "GET"
    mock_log.request_path = "/test"
    mock_log.resource_type = "res"
    mock_log.resource_id = str(uuid4())
    mock_log.details = {"info": "masked"}
    mock_log.success = True
    mock_log.error_message = None

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_log
    mock_db.execute.return_value = mock_res
    
    res = await get_audit_log_detail(mock_log.id, admin_user, mock_db)
    assert res["event_type"] == "test"

@pytest.mark.asyncio
async def test_get_audit_log_detail_not_found(mock_db, admin_user):
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    
    with pytest.raises(HTTPException) as exc:
        await get_audit_log_detail(uuid4(), admin_user, mock_db)
    assert exc.value.status_code == 404

@pytest.mark.asyncio
async def test_get_audit_log_detail_error(mock_db, admin_user):
    mock_db.execute.side_effect = Exception("DB error")
    with pytest.raises(HTTPException) as exc:
        await get_audit_log_detail(uuid4(), admin_user, mock_db)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_get_event_types_success(admin_user):
    res = await get_event_types(admin_user)
    assert "event_types" in res
    assert len(res["event_types"]) > 0

@pytest.mark.asyncio
async def test_export_audit_logs_success(mock_db, admin_user):
    mock_log = MagicMock(spec=AuditLog)
    mock_log.id = uuid4()
    mock_log.event_type = "test-event"
    mock_log.event_timestamp = datetime.now(timezone.utc)
    mock_log.actor_email = "a@b.com"
    mock_log.resource_type = "res"
    mock_log.resource_id = str(uuid4())
    mock_log.success = True
    mock_log.correlation_id = "c-1"
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [mock_log]
    mock_db.execute.return_value = mock_res
    
    # Coverage for start_date, end_date, event_type
    response = await export_audit_logs(
        admin_user, 
        mock_db, 
        start_date=datetime.now(),
        end_date=datetime.now(),
        event_type="test-event"
    )
    assert response.media_type == "text/csv"

@pytest.mark.asyncio
async def test_export_audit_logs_error(mock_db, admin_user):
    mock_db.execute.side_effect = Exception("DB error")
    with pytest.raises(HTTPException) as exc:
        await export_audit_logs(admin_user, mock_db)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_request_data_erasure_confirmation_fail(owner_user, mock_db):
    with pytest.raises(HTTPException) as exc:
        await request_data_erasure(owner_user, mock_db, confirmation="WRONG")
    assert exc.value.status_code == 400

@pytest.mark.asyncio
async def test_request_data_erasure_success(mock_db, owner_user):
    tenant_lookup = MagicMock()
    tenant_lookup.scalar_one_or_none.return_value = MagicMock(id=owner_user.tenant_id)

    delete_result = MagicMock()
    delete_result.rowcount = 5

    # 1 tenant existence check + 19 delete statements
    mock_db.execute.side_effect = [tenant_lookup] + [delete_result] * 19

    res = await request_data_erasure(owner_user, mock_db, confirmation="DELETE ALL MY DATA")

    assert res["status"] == "erasure_complete"
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_request_data_erasure_error(mock_db, owner_user):
    mock_db.execute.side_effect = Exception("DB error")
    with pytest.raises(HTTPException) as exc:
        await request_data_erasure(owner_user, mock_db, confirmation="DELETE ALL MY DATA")
    assert exc.value.status_code == 500
    assert mock_db.rollback.called
