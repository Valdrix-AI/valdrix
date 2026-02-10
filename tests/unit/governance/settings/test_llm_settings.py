import pytest
import uuid
from httpx import AsyncClient
from app.models.llm import LLMBudget
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from unittest.mock import patch

@pytest.mark.asyncio
async def test_get_llm_settings_creates_default(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """GET /llm should create default budget if it doesn't exist."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/llm")
        assert response.status_code == 200
        assert response.json()["monthly_limit_usd"] == 10.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_llm_settings(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """PUT /llm should update existing budget and keys."""
    user_id = uuid.UUID(str(mock_user_id))
    tenant_id = uuid.UUID(str(mock_tenant_id))
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="test@valdrix.io", role=UserRole.ADMIN)
    
    budget = LLMBudget(tenant_id=tenant_id, monthly_limit_usd=10.0, preferred_provider="groq")
    db.add(budget)
    await db.commit()
    
    update_data = {"monthly_limit_usd": 50.0, "preferred_provider": "openai", "openai_api_key": "sk-test"}
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put("/api/v1/settings/llm", json=update_data)
        assert response.status_code == 200
        assert response.json()["monthly_limit_usd"] == 50.0
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_get_llm_models(async_client: AsyncClient):
    """GET /llm/models should return available models."""
    response = await async_client.get("/api/v1/settings/llm/models")
    assert response.status_code == 200
    assert "groq" in response.json()
    
    # Verify pricing data import works (runtime check)
    from app.shared.llm.pricing_data import LLM_PRICING
    assert LLM_PRICING is not None

@pytest.mark.asyncio
async def test_update_llm_settings_creates_with_keys(async_client: AsyncClient, db, app):
    """PUT /llm should create settings when missing and set key flags."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    update_data = {
        "monthly_limit_usd": 25.0,
        "alert_threshold_percent": 80,
        "hard_limit": True,
        "preferred_provider": "openai",
        "preferred_model": "gpt-4o-mini",
        "openai_api_key": "sk-test",
        "groq_api_key": "gsk-test",
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.put("/api/v1/settings/llm", json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["monthly_limit_usd"] == 25.0
        assert data["has_openai_key"] is True
        assert data["has_groq_key"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_llm_settings_threshold_logging(async_client: AsyncClient, db, app):
    """PUT /llm logs threshold boundary values when settings exist."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    db.add(LLMBudget(tenant_id=tenant_id, monthly_limit_usd=10.0, preferred_provider="groq"))
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.modules.governance.api.v1.settings.llm.logger") as mock_logger, \
             patch("app.modules.governance.api.v1.settings.llm.audit_log") as mock_audit:
            response = await async_client.put(
                "/api/v1/settings/llm",
                json={
                    "monthly_limit_usd": 10.0,
                    "alert_threshold_percent": 0,
                    "hard_limit": False,
                    "preferred_provider": "groq",
                    "preferred_model": "llama-3.3-70b-versatile",
                },
            )
            assert response.status_code == 200
            assert mock_logger.info.called

            response = await async_client.put(
                "/api/v1/settings/llm",
                json={
                    "monthly_limit_usd": 10.0,
                    "alert_threshold_percent": 100,
                    "hard_limit": False,
                    "preferred_provider": "groq",
                    "preferred_model": "llama-3.3-70b-versatile",
                },
            )
            assert response.status_code == 200
            assert mock_logger.info.called
            assert mock_audit.called
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_get_llm_settings_flags(async_client: AsyncClient, db, app):
    """GET /llm should return key presence flags."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(id=user_id, tenant_id=tenant_id, email="admin@valdrix.io", role=UserRole.ADMIN)

    db.add(LLMBudget(
        tenant_id=tenant_id,
        monthly_limit_usd=10.0,
        preferred_provider="groq",
        openai_api_key="sk-test",
        claude_api_key=None,
        google_api_key="gcp-key",
        groq_api_key=None,
    ))
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get("/api/v1/settings/llm")
        assert response.status_code == 200
        data = response.json()
        assert data["has_openai_key"] is True
        assert data["has_google_key"] is True
        assert data["has_claude_key"] is False
        assert data["has_groq_key"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_llm_settings_requires_admin(async_client: AsyncClient, app):
    member = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="member@llm.io",
        role=UserRole.MEMBER,
    )
    app.dependency_overrides[get_current_user] = lambda: member
    try:
        response = await async_client.put(
            "/api/v1/settings/llm",
            json={
                "monthly_limit_usd": 10.0,
                "alert_threshold_percent": 80,
                "hard_limit": False,
                "preferred_provider": "groq",
                "preferred_model": "llama-3.3-70b-versatile",
            },
        )
        assert response.status_code == 403
        assert "Insufficient permissions" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

@pytest.mark.asyncio
async def test_update_llm_settings_validation_failure(async_client: AsyncClient, app):
    admin = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@llm.io",
        role=UserRole.ADMIN,
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        response = await async_client.put(
            "/api/v1/settings/llm",
            json={
                "monthly_limit_usd": 10.0,
                "alert_threshold_percent": 80,
                "hard_limit": False,
                "preferred_provider": "invalid",
                "preferred_model": "gpt-4o-mini",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
