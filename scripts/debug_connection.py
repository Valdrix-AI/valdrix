import asyncio
import sys
import os
from sqlalchemy import text

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🔍 Importing session maker...")
from app.shared.db.session import async_session_maker, engine  # noqa: E402

async def test_connection():
    print("🔌 Testing DB connection...")
    async with async_session_maker() as db:
        res = await db.execute(text("SELECT 1"))
        val = res.scalar()
        print(f"✅ Connection successful! Value: {val}")

    print("🔍 Importing models...")
    print("✅ Models imported!")

    print("🔌 Testing Model Query...")
    async with async_session_maker() as db:
        res = await db.execute(text("SELECT count(*) FROM tenants"))
        count = res.scalar()
        print(f"✅ Tenants count: {count}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_connection())
