import asyncio
import httpx
import os
import structlog
from app.shared.core.config import get_settings

logger = structlog.get_logger()

async def verify_greenops_api():
    """
    Performs authenticated API-level verification for GreenOps.
    Standardizes BE-OPS-01: Authenticated Verification.
    """
    settings = get_settings()
    base_url = os.getenv("API_URL", "http://localhost:8000")
    
    # Require real auth in production; allow dev defaults ONLY if not in prod
    token = os.getenv("VERIFICATION_TOKEN")
    admin_key = os.getenv("ADMIN_API_KEY") or settings.ADMIN_API_KEY
    
    if not token and not admin_key and settings.ENVIRONMENT == "production":
        print("❌ ERROR: No authentication provided (VERIFICATION_TOKEN or ADMIN_API_KEY).")
        print("Aborting GreenOps verification for safety.")
        return

    print(f"🧪 Starting Authenticated GreenOps API Verification on {base_url}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Prefer ADMIN_API_KEY if available for internal verification
        if admin_key:
            headers = {"X-Admin-API-Key": admin_key}
            print("🔑 Using Admin API Key for authentication.")
        else:
            headers = {"Authorization": f"Bearer {token}"}
            print("🔑 Using Bearer Token for authentication.")
        
        # 1. Test Intensity Forecast
        print("📡 Testing Intensity Forecast API (/api/v1/carbon/intensity)...")
        try:
            r = await client.get(f"{base_url}/api/v1/carbon/intensity?region=us-east-1&hours=12", headers=headers)
            if r.status_code == 200:
                data = r.json()
                print(f"✅ Intensity Forecast: OK (Source: {data.get('source')})")
            elif r.status_code == 401:
                print("❌ Auth Failed: 401 Unauthorized. Ensure token is valid.")
            else:
                print(f"❌ API Failed: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"❌ Connection Failed: {str(e)}")

        # 2. Test Green Schedule
        print("\n⏰ Testing Green Schedule API (/api/v1/carbon/schedule)...")
        try:
            r = await client.get(f"{base_url}/api/v1/carbon/schedule?region=us-west-2", headers=headers)
            if r.status_code == 200:
                data = r.json()
                print(f"✅ Green Schedule: OK (Recommendation: {data.get('recommendation')})")
            else:
                print(f"❌ API Failed: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"❌ Connection Failed: {str(e)}")

    print("\n🏆 GreenOps API Verification Complete.")

if __name__ == "__main__":
    asyncio.run(verify_greenops_api())
