from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException, Request

from app.models.tenant import UserRole
from app.shared.core.auth import (
    _hash_email,
    CurrentUser,
    bind_tenant_db_context,
    create_access_token,
    decode_jwt,
    get_current_user,
    get_current_user_with_db_context,
    require_tenant_access,
    requires_role_with_db_context,
)
from app.shared.core.pricing import PricingTier


TEST_SECRET = "branch_test_secret_minimum_32_bytes_for_hs256"


class _AsyncNullContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _settings(*, secret: str | None = TEST_SECRET, kid: str | None = None, is_production: bool = False):
    return SimpleNamespace(
        SUPABASE_JWT_SECRET=secret,
        JWT_SIGNING_KID=kid,
        is_production=is_production,
    )


def _auth_result_row_with_optional(
    user_id,
    tenant_id,
    *,
    role: str = UserRole.ADMIN.value,
    persona: str | None = "engineering",
    is_active: bool | None = True,
    plan=PricingTier.PRO.value,
    tenant_deleted: bool = False,
):
    result = MagicMock()
    result.one_or_none.return_value = (
        user_id,
        tenant_id,
        role,
        persona,
        is_active,
        plan,
        tenant_deleted,
    )
    return result


def _auth_result_row_without_optional(user_id, tenant_id):
    result = MagicMock()
    result.one_or_none.return_value = (
        user_id,
        tenant_id,
        UserRole.ADMIN.value,
        PricingTier.PRO.value,
        False,
    )
    return result


def _identity_result(identity_settings) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = identity_settings
    return result


@pytest.fixture(autouse=True)
def _mock_auth_settings():
    with patch("app.shared.core.auth.get_settings", return_value=_settings()):
        yield


def test_hash_email_none_returns_none() -> None:
    assert _hash_email(None) is None
    assert _hash_email("") is None


def test_create_access_token_preserves_existing_aud_and_iss() -> None:
    token = create_access_token(
        {
            "sub": "123",
            "aud": "custom-audience",
            "iss": "custom-issuer",
        },
        expires_delta=timedelta(minutes=5),
    )

    decoded = jwt.decode(
        token,
        TEST_SECRET,
        algorithms=["HS256"],
        audience="custom-audience",
    )
    assert decoded["iss"] == "custom-issuer"


def test_create_access_token_raises_when_secret_missing() -> None:
    with patch("app.shared.core.auth.get_settings", return_value=_settings(secret=None)):
        with pytest.raises(ValueError, match="SUPABASE_JWT_SECRET is not configured"):
            create_access_token({"sub": "123"})


def test_decode_jwt_raises_when_secret_missing() -> None:
    with patch("app.shared.core.auth.get_settings", return_value=_settings(secret=None)):
        with pytest.raises(ValueError, match="Missing JWT secret"):
            decode_jwt("any-token")


@pytest.mark.asyncio
async def test_get_current_user_schema_mismatch_fallback_without_optional_columns() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.side_effect = [
        Exception('column "persona" does not exist'),
        _auth_result_row_without_optional(user_id, tenant_id),
        _identity_result(None),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@example.com"},
        ),
        patch(
            "app.shared.core.auth.set_session_tenant_id",
            new_callable=AsyncMock,
        ) as mock_set_tenant,
    ):
        user = await get_current_user(request, credentials, db)

    assert user.id == user_id
    assert user.tenant_id == tenant_id
    assert user.persona.value == "engineering"
    mock_set_tenant.assert_awaited_once_with(db, tenant_id)


@pytest.mark.asyncio
async def test_get_current_user_sqlite_backend_skips_nested_probe() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(
            dialect=SimpleNamespace(name="sqlite"),
        )
    )
    db.begin_nested = MagicMock(side_effect=AssertionError("must not be called"))
    db.execute.side_effect = [
        _auth_result_row_with_optional(user_id, tenant_id),
        _identity_result(None),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@example.com"},
        ),
        patch(
            "app.shared.core.auth.set_session_tenant_id",
            new_callable=AsyncMock,
        ) as mock_set_tenant,
    ):
        user = await get_current_user(request, credentials, db)

    assert user.id == user_id
    assert user.tenant_id == tenant_id
    db.begin_nested.assert_not_called()
    mock_set_tenant.assert_awaited_once_with(db, tenant_id)


@pytest.mark.asyncio
async def test_get_current_user_sqlite_schema_mismatch_rolls_back_then_retries() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.get_bind = MagicMock(
        return_value=SimpleNamespace(
            dialect=SimpleNamespace(name="sqlite"),
        )
    )
    db.begin_nested = MagicMock(side_effect=AssertionError("must not be called"))
    db.rollback = AsyncMock()
    db.execute.side_effect = [
        Exception('column "persona" does not exist'),
        _auth_result_row_without_optional(user_id, tenant_id),
        _identity_result(None),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@example.com"},
        ),
        patch(
            "app.shared.core.auth.set_session_tenant_id",
            new_callable=AsyncMock,
        ) as mock_set_tenant,
    ):
        user = await get_current_user(request, credentials, db)

    assert user.id == user_id
    assert user.tenant_id == tenant_id
    db.begin_nested.assert_not_called()
    db.rollback.assert_awaited_once()
    mock_set_tenant.assert_awaited_once_with(db, tenant_id)


@pytest.mark.asyncio
async def test_get_current_user_invalid_persona_then_disabled_user_denied() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.return_value = _auth_result_row_with_optional(
        user_id,
        tenant_id,
        persona="not-a-real-persona",
        is_active=False,
    )

    with patch(
        "app.shared.core.auth.decode_jwt",
        return_value={"sub": str(user_id), "email": "user@example.com"},
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials, db)

    assert exc.value.status_code == 403
    assert "disabled" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_get_current_user_enforces_sso_allowed_email_domain() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.side_effect = [
        _auth_result_row_with_optional(user_id, tenant_id),
        _identity_result(
            SimpleNamespace(
                sso_enabled=True,
                allowed_email_domains=["company.com"],
            )
        ),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@other.com"},
        ),
        patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials, db)

    assert exc.value.status_code == 403
    assert "domain is not allowed" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_get_current_user_allows_sso_email_domain_match() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.side_effect = [
        _auth_result_row_with_optional(user_id, tenant_id),
        _identity_result(
            SimpleNamespace(
                sso_enabled=True,
                allowed_email_domains=["company.com"],
            )
        ),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@company.com"},
        ),
        patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock),
    ):
        user = await get_current_user(request, credentials, db)

    assert user.id == user_id
    assert user.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_get_current_user_identity_policy_error_skips_in_nonprod() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.side_effect = [
        _auth_result_row_with_optional(user_id, tenant_id),
        RuntimeError("identity settings lookup failed"),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@company.com"},
        ),
        patch(
            "app.shared.core.auth.get_settings",
            return_value=_settings(is_production=False),
        ),
        patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock),
    ):
        user = await get_current_user(request, credentials, db)

    assert user.id == user_id


@pytest.mark.asyncio
async def test_get_current_user_identity_policy_error_fails_closed_in_production() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    request = MagicMock(spec=Request)
    request.state = MagicMock()
    credentials = SimpleNamespace(credentials="token")
    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncNullContext())
    db.execute.side_effect = [
        _auth_result_row_with_optional(user_id, tenant_id),
        RuntimeError("identity settings lookup failed"),
    ]

    with (
        patch(
            "app.shared.core.auth.decode_jwt",
            return_value={"sub": str(user_id), "email": "user@company.com"},
        ),
        patch(
            "app.shared.core.auth.get_settings",
            return_value=_settings(is_production=True),
        ),
        patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request, credentials, db)

    assert exc.value.status_code == 500
    assert "identity policy enforcement failed" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_bind_and_get_current_user_with_db_context_bind_tenant_id() -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        email="user@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    db = AsyncMock()

    with patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock) as mock_set:
        await bind_tenant_db_context(user, db)
        returned = await get_current_user_with_db_context(user, db)

    assert returned == user
    assert mock_set.await_count == 2
    mock_set.assert_any_await(db, tenant_id)


@pytest.mark.asyncio
async def test_db_context_helpers_skip_binding_when_tenant_missing() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="user@example.com",
        tenant_id=None,
        role=UserRole.MEMBER,
        tier=PricingTier.FREE,
    )
    db = AsyncMock()
    checker = requires_role_with_db_context(UserRole.MEMBER.value)

    with patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock) as mock_set:
        await bind_tenant_db_context(user, db)
        returned_user = await get_current_user_with_db_context(user, db)
        checked_user = await checker(user, db)

    assert returned_user == user
    assert checked_user == user
    mock_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_requires_role_with_db_context_binds_tenant_id() -> None:
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        email="member@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    db = AsyncMock()
    checker = requires_role_with_db_context(UserRole.MEMBER.value)

    with patch("app.shared.core.auth.set_session_tenant_id", new_callable=AsyncMock) as mock_set:
        result = await checker(user, db)

    assert result == user
    mock_set.assert_awaited_once_with(db, tenant_id)


def test_require_tenant_access_still_denies_missing_tenant_context() -> None:
    user = CurrentUser(id=uuid4(), email="user@example.com", tenant_id=None)
    with pytest.raises(HTTPException):
        require_tenant_access(user)
