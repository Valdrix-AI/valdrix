import httpx
import asyncio
import json

base_url = "http://localhost:8000"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL291ZmxuamdzeWZxcXZqcWxwY2ljLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJiOTMxNDZkOS00OTkzLTQyY2UtODM2Mi05NzFiYmE5ZTc5ZjAiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzY5OTg1MDQzLCJpYXQiOjE3Njk4OTg2NDMsImVtYWlsIjoidGVzdEBjbG91ZHNlbnRpbmVsLmNvbSIsInJvbGUiOiJhdXRoZW50aWNhdGVkIn0.1zvqTHjPmgZg33fQv309LKW0HrJUbD65GlkaecUlgSA"

async def main():
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        # 1. Verify Swagger Assets
        print("Checking Swagger Assets...")
        r = await client.get(f"{base_url}/static/swagger-ui-bundle.js")
        if r.status_code == 200:
            print("Swagger Assets: OK")
        else:
            print(f"Swagger Assets Failed: {r.status_code}")

        # 2. Get CSRF Token
        print("\nGetting CSRF token...")
        try:
            r = await client.get(f"{base_url}/api/v1/public/csrf")
            print(f"CSRF Response: {r.status_code} {r.text}")
            csrf_token = r.json().get("csrf_token")
            cookies = r.cookies
            print(f"Got Cookies: {dict(cookies)}")
            headers = {
                "Authorization": f"Bearer {token}",
                "X-CSRF-Token": csrf_token,
                "Content-Type": "application/json"
            }
        except Exception as e:
            print(f"CSRF Failed: {repr(e)}")
            return

        # 3. Onboard
        print("\nAttempting Onboarding...")
        onboard_payload = {
            "tenant_name": "Final Verification Tenant",
            "admin_email": "test@cloudsentinel.com"
        }
        try:
            r = await client.post(
                f"{base_url}/api/v1/settings/onboard",
                json=onboard_payload,
                headers=headers,
                cookies=cookies
            )
            print(f"Onboarding Response: {r.status_code} {r.text}")
        except Exception as e:
            print(f"Onboarding Failed: {repr(e)}")

        # 4. Zombie Scan (Analyze=True)
        print("\nAttempting Zombie Scan...")
        try:
            r = await client.get(
                f"{base_url}/api/v1/zombies?analyze=true",
                headers=headers,
                cookies=cookies
            )
            print(f"Zombie Scan Response: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                print(f"AI Analysis Present: {'ai_analysis' in data}")
                if 'ai_analysis' in data:
                    print(f"Analysis Summary: {str(data['ai_analysis'].get('summary'))[:50]}...")
            else:
                print(r.text)
        except Exception as e:
            print(f"Zombie Scan Failed: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(main())
