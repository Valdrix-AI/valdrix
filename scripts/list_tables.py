import asyncio
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.shared.db.session import async_session_maker


async def list_tables():
    try:
        async with async_session_maker() as db:
            res = await db.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            tables = res.fetchall()
            print("Existing tables in 'public' schema:")
            for t in tables:
                print(f" - {t[0]}")
    except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError) as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(list_tables())
