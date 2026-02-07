import pytest
from httpx import AsyncClient
from unittest.mock import patch

@pytest.mark.asyncio
async def test_get_csrf_token(async_client: AsyncClient):
    """GET /csrf should return a token and set a cookie."""
    response = await async_client.get("/api/v1/public/csrf")
    assert response.status_code == 200
    data = response.json()
    assert "csrf_token" in data
    # Check for fastapi-csrf-token cookie in headers
    cookie_header = response.headers.get("set-cookie", "")
    assert "fastapi-csrf-token" in cookie_header

@pytest.mark.asyncio
async def test_run_public_assessment(async_client: AsyncClient):
    """POST /assessment should trigger FreeAssessmentService."""
    mock_result = {"potential_savings": 250.0, "zombies_found": 12}
    
    with patch("app.modules.governance.api.v1.public.assessment_service.run_assessment", return_value=mock_result):
        response = await async_client.post(
            "/api/v1/public/assessment", 
            json={"aws_account_id": "123456789012"}
        )
        
    assert response.status_code == 200
    assert response.json() == mock_result

@pytest.mark.asyncio
async def test_run_public_assessment_validation_error(async_client: AsyncClient):
    """POST /assessment should return 400 on ValueError."""
    # Valdrix exception format: {"error": "...", "code": "VALUE_ERROR", "message": "..."}
    with patch("app.modules.governance.api.v1.public.assessment_service.run_assessment", side_effect=ValueError("Invalid account")):
        response = await async_client.post(
            "/api/v1/public/assessment", 
            json={"aws_account_id": "invalid"}
        )
    assert response.status_code == 400
    data = response.json()
    assert data["code"] == "VALUE_ERROR"
    assert data["message"] == "Invalid account"
