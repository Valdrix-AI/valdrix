import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, HTTPException
from app.shared.core.auth import get_current_user, decode_jwt, CurrentUser, get_current_user_from_jwt, requires_role, require_tenant_access
from uuid import uuid4
import jwt
from datetime import datetime, timezone, timedelta

@pytest.fixture
def mock_settings():
    with patch("app.shared.core.auth.get_settings") as mock:
        mock.return_value.SUPABASE_JWT_SECRET = "test_secret"
        yield mock.return_value

@pytest.mark.asyncio
async def test_decode_jwt_success(mock_settings):
    payload = {"sub": str(uuid4()), "aud": "authenticated", "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()}
    token = jwt.encode(payload, "test_secret", algorithm="HS256")
    
    decoded = decode_jwt(token)
    assert decoded["sub"] == payload["sub"]

@pytest.mark.asyncio
async def test_decode_jwt_expired(mock_settings):
    payload = {"sub": str(uuid4()), "aud": "authenticated", "exp": (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()}
    token = jwt.encode(payload, "test_secret", algorithm="HS256")
    
    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail

@pytest.mark.asyncio
async def test_get_current_user_success(mock_settings):
    user_id = uuid4()
    tenant_id = uuid4()
    email = "test@example.com"
    token_payload = {"sub": str(user_id), "aud": "authenticated"}
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    
    mock_request = MagicMock(spec=Request)
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    mock_db = AsyncMock()
    
    # Mock DB response
    mock_user = MagicMock(id=user_id, tenant_id=tenant_id, email=email, role="admin")
    mock_res = MagicMock()
    # row = (user, plan)
    mock_res.one_or_none.return_value = (mock_user, "growth")
    mock_db.execute.return_value = mock_res
    
    user = await get_current_user(mock_request, mock_credentials, mock_db)
    
    assert user.id == user_id
    assert user.tier == "growth"
    assert mock_request.state.tenant_id == tenant_id

@pytest.mark.asyncio
async def test_get_current_user_not_found(mock_settings):
    token_payload = {"sub": str(uuid4()), "aud": "authenticated"}
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    mock_db = AsyncMock()
    mock_res = MagicMock()
    mock_res.one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    
    with pytest.raises(HTTPException) as exc:
        await get_current_user(MagicMock(spec=Request), mock_credentials, mock_db)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_requires_role_hierarchy_success():
    user = CurrentUser(id=uuid4(), email="a@b.com", role="admin", tier="starter")
    # req_role="member" should pass for "admin"
    checker = requires_role("member")
    res = checker(user)
    assert res == user

@pytest.mark.asyncio
async def test_requires_role_forbidden():
    user = CurrentUser(id=uuid4(), email="a@b.com", role="member", tier="starter")
    checker = requires_role("admin")
    with pytest.raises(HTTPException) as exc:
        checker(user)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_require_tenant_access_success():
    tid = uuid4()
    user = CurrentUser(id=uuid4(), email="a@b.com", tenant_id=tid)
    res = require_tenant_access(user)
    assert res == tid

@pytest.mark.asyncio
async def test_require_tenant_access_missing():
    user = CurrentUser(id=uuid4(), email="a@b.com", tenant_id=None)
    with pytest.raises(HTTPException) as exc:
        require_tenant_access(user)
    assert exc.value.status_code == 403
@pytest.mark.asyncio
async def test_decode_jwt_invalid(mock_settings):
    with pytest.raises(HTTPException) as exc:
        decode_jwt("invalid.token.payload")
    assert exc.value.status_code == 401
    assert "Invalid token" in exc.value.detail

@pytest.mark.asyncio
async def test_get_current_user_from_jwt_success(mock_settings):
    user_id = str(uuid4())
    token_payload = {"sub": user_id, "email": "test@example.com", "aud": "authenticated"}
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    
    user = await get_current_user_from_jwt(mock_credentials)
    assert str(user.id) == user_id
    assert user.email == "test@example.com"

@pytest.mark.asyncio
async def test_get_current_user_from_jwt_no_credentials():
    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_jwt(None)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_from_jwt_missing_sub(mock_settings):
    token_payload = {"email": "test@example.com", "aud": "authenticated"} # Missing sub
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    
    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_jwt(mock_credentials)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_no_credentials():
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await get_current_user(mock_request, None, mock_db)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_missing_sub(mock_settings):
    token_payload = {"email": "test@example.com", "aud": "authenticated"}
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock()
    
    with pytest.raises(HTTPException) as exc:
        await get_current_user(mock_request, mock_credentials, mock_db)
    assert exc.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_db_error(mock_settings):
    user_id = str(uuid4())
    token_payload = {"sub": user_id, "aud": "authenticated"}
    token = jwt.encode(token_payload, "test_secret", algorithm="HS256")
    mock_credentials = MagicMock()
    mock_credentials.credentials = token
    mock_request = MagicMock(spec=Request)
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB Fail")
    
    with pytest.raises(HTTPException) as exc:
        await get_current_user(mock_request, mock_credentials, mock_db)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_requires_role_owner_bypass():
    user = CurrentUser(id=uuid4(), email="owner@b.com", role="owner")
    checker = requires_role("admin")
    res = checker(user)
    assert res == user

@pytest.mark.asyncio
async def test_requires_role_unknown_role():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        CurrentUser(id=uuid4(), email="a@b.com", role="unknown")

@pytest.mark.asyncio
async def test_requires_role_unknown_required_role():
    user = CurrentUser(id=uuid4(), email="a@b.com", role="member")
    # This will raise ValueError when calling UserRole("unknown_required")
    with pytest.raises(ValueError):
        checker = requires_role("unknown_required")
        checker(user)

@pytest.mark.asyncio
async def test_require_tenant_access_failure():
    user = CurrentUser(id=uuid4(), email="a@b.com", tenant_id=None)
    with pytest.raises(HTTPException) as exc:
        require_tenant_access(user)
    assert exc.value.status_code == 403
    assert "Tenant context required" in exc.value.detail
