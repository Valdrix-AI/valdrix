import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

async def test_connection():
    # Try session pooler (port 5432)
    url = "postgresql+asyncpg://postgres.ouflnjgsyfqqvjqlpcic:GgIFxzzGu19LUPZM@aws-1-us-east-1.pooler.supabase.com:5432/postgres"
    print(f"Testing session pooler to: {url}")
    try:
        engine = create_async_engine(url)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT 1"))
            print(f"Success: {res.scalar()}")
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_connection())
