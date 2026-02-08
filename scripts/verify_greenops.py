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
    
    # Use the same mock token pattern as verify_backend_e2e for dry-run verification
    # In production, this would be a real service token.
    token = os.getenv("VERIFICATION_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL291ZmxuamdzeWZxcXZqcWxwY2ljLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJiOTMxNDZkOS00OTkzLTQyY2UtODM2Mi05NzFiYmE5ZTc5ZjAiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcwMzQyMjQwLCJpYXQiOjE3NzAyNTU4NDAsImVtYWlsIjoyIn0.7") 
    
    print(f"🧪 Starting Authenticated GreenOps API Verification on {base_url}...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"Authorization": f"Bearer {token}"}
        
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
