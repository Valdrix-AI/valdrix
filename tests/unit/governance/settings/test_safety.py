import pytest
import uuid
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
from app.models.tenant import UserRole
from app.shared.core.auth import CurrentUser, get_current_user
from types import SimpleNamespace


class _FatalTestSignal(BaseException):
    """Sentinel fatal error used to assert broad Exception handlers do not swallow BaseException."""


def _exception_group_contains(
    error: BaseException, exc_type: type[BaseException]
) -> bool:
    if isinstance(error, exc_type):
        return True
    if isinstance(error, BaseExceptionGroup):
        return any(
            _exception_group_contains(nested, exc_type) for nested in error.exceptions
        )
    return False


@pytest.mark.asyncio
async def test_get_safety_status(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    """GET /safety should return circuit breaker status."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    # Mock CircuitBreaker
    mock_cb = AsyncMock()
    mock_cb.state = AsyncMock()
    mock_cb.state.get.side_effect = lambda key, default: {
        "state": "closed",
        "failure_count": 0,
        "daily_savings": 50.0,
        "last_failure_at": None,
    }.get(key, default)
    mock_cb.can_execute.return_value = True

    app.dependency_overrides[get_current_user] = lambda: mock_user
    # Patch the source of lazy import
    with patch(
        "app.shared.remediation.circuit_breaker.get_circuit_breaker",
        return_value=mock_cb,
    ):
        try:
            response = await async_client.get("/api/v1/settings/safety")
            assert response.status_code == 200
            data = response.json()
            assert data["circuit_state"] == "closed"
            assert data["daily_savings_used"] == 50.0
            assert data["can_execute"] is True
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_reset_circuit_breaker(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    """POST /safety/reset should call circuit_breaker.reset()."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    mock_cb = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.shared.remediation.circuit_breaker.get_circuit_breaker",
        return_value=mock_cb,
    ):
        try:
            response = await async_client.post("/api/v1/settings/safety/reset")
            assert response.status_code == 200
            assert response.json()["status"] == "reset"
            mock_cb.reset.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_safety_status_exception_returns_defaults(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with (
        patch(
            "app.shared.remediation.circuit_breaker.get_circuit_breaker",
            side_effect=RuntimeError("redis down"),
        ),
        patch(
            "app.shared.core.config.get_settings",
            return_value=SimpleNamespace(CIRCUIT_BREAKER_MAX_DAILY_SAVINGS=123.0),
        ),
    ):
        try:
            response = await async_client.get("/api/v1/settings/safety")
            assert response.status_code == 200
            data = response.json()
            assert data["circuit_state"] == "unknown"
            assert data["daily_savings_used"] == 0.0
            assert data["daily_savings_limit"] == 123.0
            assert data["can_execute"] is False
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_reset_circuit_breaker_failure(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="test@valdrics.io", role=UserRole.ADMIN
    )

    mock_cb = AsyncMock()
    mock_cb.reset.side_effect = RuntimeError("redis down")

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.shared.remediation.circuit_breaker.get_circuit_breaker",
        return_value=mock_cb,
    ):
        try:
            response = await async_client.post("/api/v1/settings/safety/reset")
            assert response.status_code == 500
            body = response.json()
            assert "Failed to reset circuit breaker" in (
                body.get("message") or body.get("error") or ""
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_reset_circuit_breaker_requires_admin(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="member@valdrics.io", role=UserRole.MEMBER
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post("/api/v1/settings/safety/reset")
        assert response.status_code in {401, 403}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_safety_status_does_not_swallow_fatal_exceptions(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="fatal@valdrics.io", role=UserRole.ADMIN
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.shared.remediation.circuit_breaker.get_circuit_breaker",
        side_effect=_FatalTestSignal(),
    ):
        try:
            with pytest.raises(BaseExceptionGroup) as exc_info:
                await async_client.get("/api/v1/settings/safety")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
    assert _exception_group_contains(exc_info.value, _FatalTestSignal)


@pytest.mark.asyncio
async def test_reset_circuit_breaker_does_not_swallow_fatal_exceptions(
    async_client: AsyncClient, mock_user_id, mock_tenant_id, app
):
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(
        id=user_id, tenant_id=tenant_id, email="fatal@valdrics.io", role=UserRole.ADMIN
    )

    mock_cb = AsyncMock()
    mock_cb.reset.side_effect = _FatalTestSignal()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with patch(
        "app.shared.remediation.circuit_breaker.get_circuit_breaker",
        return_value=mock_cb,
    ):
        try:
            with pytest.raises(BaseExceptionGroup) as exc_info:
                await async_client.post("/api/v1/settings/safety/reset")
        finally:
            app.dependency_overrides.pop(get_current_user, None)
    assert _exception_group_contains(exc_info.value, _FatalTestSignal)
