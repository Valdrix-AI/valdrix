import asyncio
from sqlalchemy import text
from app.shared.db.session import async_session_maker


async def run():
    async with async_session_maker() as session:
        with open("scripts/archive_partitions.sql") as f:
            sql = f.read()
            # Split by double dollar signs if necessary, but sqlalchemy text() should handle it
            await session.execute(text(sql))
            await session.commit()
            print("Successfully created archive_old_cost_partitions function.")


if __name__ == "__main__":
    asyncio.run(run())
