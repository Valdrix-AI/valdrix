import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_public_assessment_endpoint() -> None:
    """Verify that the public assessment endpoint works without auth."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        payload = {
            "email": "lead@example.com",
            "monthly_spend": 1000.0,
            "data": [{"service": "EC2", "cost": 50}, {"service": "S3", "cost": 20}],
        }
        response = await ac.post("/api/v1/public/assessment", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # Heuristic: 18% of 1000 = 180
        assert data["summary"]["estimated_savings_usd"] == 180.0
        assert "next_steps" in data


@pytest.mark.asyncio
async def test_public_assessment_rate_limiting() -> None:
    """Verify rate limiting is disabled during testing."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        payload = {"email": "spam@example.com", "monthly_spend": 500.0}
        # Hit it multiple times; should stay 200 because decorator is no-op
        for _ in range(3):
            response = await ac.post("/api/v1/public/assessment", json=payload)
            assert response.status_code == 200
