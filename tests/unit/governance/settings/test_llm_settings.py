import pytest
import uuid
from httpx import AsyncClient
from app.models.llm import LLMBudget
from app.shared.core.auth import CurrentUser, get_current_user, UserRole

@pytest.mark.asyncio
async def test_get_llm_settings_creates_default(async_client: AsyncClient, db, mock_user_id, mock_tenant_id, app):
    """GET /llm should create default budget if it doesn't exist."""
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
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
    user_id = uuid.UUID(mock_user_id)
    tenant_id = uuid.UUID(mock_tenant_id)
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
