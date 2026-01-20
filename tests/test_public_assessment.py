
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_public_assessment_endpoint():
    """Verify that the public assessment endpoint works without auth."""
    # We need to mock the analyzer and selector to avoid real LLM calls
    mock_analysis = {
        "insights": ["Insight 1", "Insight 2", "Insight 3", "Insight 4"],
        "recommendations": ["Rec 1", "Rec 2", "Rec 3"],
        "potential_savings": 100.0
    }
    
    with patch("app.services.llm.analyzer.FinOpsAnalyzer.analyze", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_analysis
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {
                "data": [
                    {"service": "EC2", "cost": 50},
                    {"service": "S3", "cost": 20}
                ]
            }
            response = await ac.post("/api/v1/public/assessment", json=payload)
            
            assert response.status_code == 200
            data = response.json()
            assert "assessment_id" in data
            assert data["summary"]["total_cost"] == 70.0
            assert len(data["insights"]) == 3 # Limited to 3
            assert len(data["recommendations"]) == 2 # Limited to 2
            assert "next_steps" in data

@pytest.mark.asyncio
async def test_public_assessment_rate_limiting():
    """Verify rate limiting is disabled during testing."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {"data": [{"service": "EC2", "cost": 50}]}
        # Hit it multiple times; should stay 200 because decorator is no-op
        for _ in range(3):
            response = await ac.post("/api/v1/public/assessment", json=payload)
            assert response.status_code == 200
