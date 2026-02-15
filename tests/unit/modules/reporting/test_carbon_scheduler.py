import pytest
from app.modules.reporting.domain.carbon_scheduler import CarbonAwareScheduler


@pytest.mark.asyncio
async def test_carbon_simulation_diurnal():
    scheduler = CarbonAwareScheduler()
    # us-east-1 has peak solar at 13 UTC
    # Simulation should show lower intensity around 13 UTC

    intensities = []
    # Manually get profile for cleaner test
    from app.modules.reporting.domain.carbon_scheduler import REGION_CARBON_PROFILES

    profile = REGION_CARBON_PROFILES["us-east-1"]

    for hour in range(24):
        intensity = scheduler._simulate_intensity(profile, hour)
        intensities.append((hour, intensity))

    # Sort by intensity
    sorted_intensities = sorted(intensities, key=lambda x: x[1])

    # Best hour should be around 13 (peak solar)
    best_hour = sorted_intensities[0][0]
    assert 11 <= best_hour <= 15

    # Worst hour should be far from 13
    worst_hour = sorted_intensities[-1][0]
    assert worst_hour < 6 or worst_hour > 20


@pytest.mark.asyncio
async def test_forecast_api_logic():
    scheduler = CarbonAwareScheduler()
    forecast = await scheduler.get_intensity_forecast("us-east-1", hours=6)

    assert len(forecast) == 6
    assert "intensity_gco2_kwh" in forecast[0]
    assert "level" in forecast[0]
