import pytest

from app.shared.lead_gen.assessment import FreeAssessmentService


@pytest.mark.asyncio
async def test_run_assessment_requires_email():
    service = FreeAssessmentService()
    with pytest.raises(ValueError, match="Email is required"):
        await service.run_assessment({})


@pytest.mark.asyncio
async def test_run_assessment_default_spend():
    service = FreeAssessmentService()
    result = await service.run_assessment({"email": "test@example.com"})

    assert result["status"] == "success"
    assert result["summary"]["estimated_savings_usd"] == 0.0
    assert result["summary"]["potential_optimization_percent"] == 18.2


@pytest.mark.asyncio
async def test_run_assessment_calculates_savings():
    service = FreeAssessmentService()
    result = await service.run_assessment(
        {"email": "test@example.com", "monthly_spend": 1000}
    )

    assert result["summary"]["estimated_savings_usd"] == 180.0


@pytest.mark.asyncio
async def test_run_assessment_accepts_numeric_string():
    service = FreeAssessmentService()
    result = await service.run_assessment(
        {"email": "test@example.com", "monthly_spend": "500.5"}
    )

    assert result["summary"]["estimated_savings_usd"] == 90.09


@pytest.mark.asyncio
async def test_run_assessment_rejects_invalid_monthly_spend():
    service = FreeAssessmentService()
    with pytest.raises(ValueError, match="monthly_spend must be a number"):
        await service.run_assessment(
            {"email": "test@example.com", "monthly_spend": "nope"}
        )


@pytest.mark.asyncio
async def test_run_assessment_rejects_negative_spend():
    service = FreeAssessmentService()
    with pytest.raises(ValueError, match="monthly_spend must be non-negative"):
        await service.run_assessment({"email": "test@example.com", "monthly_spend": -1})
