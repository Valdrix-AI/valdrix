import asyncio
from sqlalchemy import text
from app.shared.db.session import async_session_maker

async def check():
    try:
        async with async_session_maker() as db:
            result = await db.execute(text('SELECT 1'))
            row = result.fetchone()
            print(f"DB CONNECTION SUCCESS: {row[0]}")
    except Exception as e:
        print(f"DB CONNECTION ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(check())
