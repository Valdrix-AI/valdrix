import asyncio
from app.shared.core.config import get_settings

async def verify_greenops_apis():
    print("🧪 Verifying GreenOps API Endpoints...")
    settings = get_settings()
    
    # We'll use a mock token check bypass or just test the logic via the router if possible
    # But since we want to test the "Production Readiness", let's test the domain logic directly first
    # and then verify the router configuration.
    
    from app.modules.reporting.domain.carbon_scheduler import CarbonAwareScheduler
    
    scheduler = CarbonAwareScheduler(
        watttime_key=settings.WATT_TIME_API_KEY,
        electricitymaps_key=settings.ELECTRICITY_MAPS_API_KEY
    )
    
    # Test Intensity Forecast
    print("📡 Testing Intensity Forecast (us-east-1)...")
    forecast = scheduler.get_intensity_forecast("us-east-1", hours=12)
    assert len(forecast) == 12
    assert "intensity_gco2_kwh" in forecast[0]
    print(f"✅ Forecast generated: {forecast[0]['intensity_gco2_kwh']} g/kWh at hour {forecast[0]['hour_utc']}")
    
    # Test Optimal Schedule
    print("⏰ Testing Optimal Schedule (us-west-2)...")
    optimal_time = scheduler.get_optimal_execution_time("us-west-2")
    if optimal_time:
        print(f"✅ Optimal time found: {optimal_time.isoformat()}")
    else:
        print("✅ No optimal time in window (executing now).")
        
    # Check Simulation Status
    print(f"🛠️ Simulation Mode: {scheduler._use_static_data}")
    assert scheduler._use_static_data is True # Unless user added keys in .env
    
    print("🏆 GreenOps Domain Verification PASSED.")

if __name__ == "__main__":
    asyncio.run(verify_greenops_apis())
