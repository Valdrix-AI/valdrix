import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from app.shared.core.auth import get_current_user, get_current_user_from_jwt, UserRole
from app.shared.core.pricing import PricingTier


class _AsyncNullContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_get_current_user_from_jwt_missing_email():
    token_payload = {"sub": str(uuid4()), "aud": "authenticated"}
    token = MagicMock()
    token.credentials = MagicMock()

    with patch("app.shared.core.auth.decode_jwt", return_value=token_payload):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        with pytest.raises(HTTPException) as exc:
            await get_current_user_from_jwt(credentials)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_sets_request_state_and_rls():
    user_id = uuid4()
    tenant_id = uuid4()
    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="token"
    )

    mock_db = AsyncMock()
    mock_res_auth = MagicMock()
    mock_res_auth.one_or_none.return_value = (
        user_id,
        tenant_id,
        UserRole.ADMIN.value,
        "engineering",
        True,
        PricingTier.STARTER.value,
        False,
    )
    mock_res_identity = MagicMock()
    mock_res_identity.scalar_one_or_none.return_value = None
    mock_db.execute.side_effect = [mock_res_auth, mock_res_identity]
    mock_db.begin_nested = MagicMock(return_value=_AsyncNullContext())

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "u@e.com"},
        ),
        patch(
            "app.shared.core.auth.set_session_tenant_id", new=AsyncMock()
        ) as mock_set,
    ):
        user = await get_current_user(mock_request, mock_credentials, mock_db)

    assert user.tenant_id == tenant_id
    assert mock_request.state.tenant_id == tenant_id
    assert mock_request.state.user_id == user_id
    assert mock_request.state.tier == PricingTier.STARTER
    mock_set.assert_awaited_once_with(mock_db, tenant_id)
