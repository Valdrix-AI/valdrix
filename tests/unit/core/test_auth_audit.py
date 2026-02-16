import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
import jwt

from app.shared.core.auth import (
    create_access_token,
    decode_jwt,
    get_current_user_from_jwt,
    get_current_user,
    requires_role,
    require_tenant_access,
    CurrentUser,
)
from app.models.tenant import UserRole
from app.shared.core.pricing import PricingTier


# Mock settings
@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.shared.core.auth.get_settings") as mock:
        mock.return_value.SUPABASE_JWT_SECRET = "supersecretkey"
        yield mock


def test_create_access_token():
    data = {"sub": "123", "email": "test@example.com"}
    token = create_access_token(data)
    decoded = jwt.decode(
        token, "supersecretkey", algorithms=["HS256"], audience="authenticated"
    )
    assert decoded["sub"] == "123"
    assert decoded["email"] == "test@example.com"
    assert decoded["iss"] == "supabase"
    assert "exp" in decoded


def test_create_access_token_with_delta():
    data = {"sub": "456"}
    delta = timedelta(minutes=5)
    token = create_access_token(data, expires_delta=delta)
    decoded = jwt.decode(
        token, "supersecretkey", algorithms=["HS256"], audience="authenticated"
    )
    assert decoded["sub"] == "456"
    # Basic check that it's within 5 min
    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    now = datetime.now(timezone.utc)
    assert (exp - now).total_seconds() <= 305


def test_decode_jwt_valid():
    token = jwt.encode(
        {
            "sub": "123",
            "aud": "authenticated",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "supersecretkey",
        algorithm="HS256",
    )
    payload = decode_jwt(token)
    assert payload["sub"] == "123"


def test_decode_jwt_expired():
    token = jwt.encode(
        {
            "sub": "123",
            "aud": "authenticated",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        },
        "supersecretkey",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail


def test_decode_jwt_invalid_signature():
    token = jwt.encode(
        {"sub": "123", "aud": "authenticated"}, "wrongkey", algorithm="HS256"
    )
    with pytest.raises(HTTPException) as exc:
        decode_jwt(token)
    assert exc.value.status_code == 401
    assert "Invalid token" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_success():
    user_id = str(uuid4())
    token = jwt.encode(
        {"sub": user_id, "email": "test@example.com", "aud": "authenticated"},
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token

    user = await get_current_user_from_jwt(credentials)
    assert str(user.id) == user_id
    assert user.email == "test@example.com"


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_no_creds():
    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_jwt(None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_invalid_payload():
    token = jwt.encode(
        {"email": "test@example.com", "aud": "authenticated"},  # Missing sub
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token
    with pytest.raises(HTTPException) as exc:
        await get_current_user_from_jwt(credentials)
    assert exc.value.status_code == 401
    assert "Invalid token payload" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_success():
    user_id = uuid4()
    tenant_id = uuid4()

    token = jwt.encode(
        {"sub": str(user_id), "email": "test@example.com", "aud": "authenticated"},
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token

    request = MagicMock(spec=Request)
    request.state = MagicMock()

    # Mock DB result
    mock_db = AsyncMock()

    mock_result_auth = MagicMock()
    mock_result_auth.one_or_none.return_value = (
        user_id,
        tenant_id,
        UserRole.ADMIN.value,
        "engineering",
        True,
        PricingTier.PRO,
    )
    mock_result_identity = MagicMock()
    mock_result_identity.scalar_one_or_none.return_value = None
    mock_db.execute.side_effect = [mock_result_auth, mock_result_identity]

    with patch(
        "app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock
    ) as mock_rls:
        user = await get_current_user(request, credentials, mock_db)

        assert user.id == user_id
        assert user.tenant_id == tenant_id
        assert user.tier == PricingTier.PRO
        assert request.state.tenant_id == tenant_id
        assert request.state.tier == PricingTier.PRO
        mock_rls.assert_called_with(mock_db, tenant_id)


@pytest.mark.asyncio
async def test_get_current_user_not_found():
    token = jwt.encode(
        {"sub": str(uuid4()), "email": "test@example.com", "aud": "authenticated"},
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token

    mock_db = AsyncMock()
    # Ensure execute returns a mock that has on_or_none
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    request = MagicMock(spec=Request)

    # Mock logger to avoid structlog issues
    with patch("app.shared.core.auth.logger"):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials, mock_db)

        assert exc.value.status_code == 403
        assert "User not found" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_no_creds():
    with pytest.raises(HTTPException) as exc:
        await get_current_user(MagicMock(), None, AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_invalid_payload():
    token = jwt.encode(
        {"email": "test@example.com", "aud": "authenticated"},  # Missing sub
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token
    with pytest.raises(HTTPException) as exc:
        await get_current_user(MagicMock(), credentials, AsyncMock())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_unexpected_error():
    token = jwt.encode(
        {"sub": str(uuid4()), "email": "test@example.com", "aud": "authenticated"},
        "supersecretkey",
        algorithm="HS256",
    )
    credentials = MagicMock()
    credentials.credentials = token
    mock_db = AsyncMock()
    mock_db.execute.side_effect = Exception("DB Exploded")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(MagicMock(), credentials, mock_db)
    assert exc.value.status_code == 500


def test_requires_role_success():
    checker = requires_role("admin")

    user = CurrentUser(id=uuid4(), email="a@b.com", role=UserRole.ADMIN)
    result = checker(user)
    assert result == user

    user_owner = CurrentUser(id=uuid4(), email="a@b.com", role=UserRole.OWNER)
    result = checker(user_owner)
    assert result == user_owner


def test_requires_role_forbidden():
    checker = requires_role("admin")
    user = CurrentUser(id=uuid4(), email="a@b.com", role=UserRole.MEMBER)

    with pytest.raises(HTTPException) as exc:
        checker(user)
    assert exc.value.status_code == 403


def test_require_tenant_access():
    user = CurrentUser(id=uuid4(), email="a@b.com", tenant_id=uuid4())
    assert require_tenant_access(user) == user.tenant_id

    user_no_tenant = CurrentUser(id=uuid4(), email="a@b.com", tenant_id=None)
    with pytest.raises(HTTPException) as exc:
        require_tenant_access(user_no_tenant)
    assert exc.value.status_code == 403
