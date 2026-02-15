import asyncio
from app.shared.db.session import async_session_maker
from sqlalchemy import select
from app.models.remediation import Remediation


async def check_zombies():
    async with async_session_maker() as session:
        try:
            res = await session.execute(select(Remediation))
            zombies = res.scalars().all()
            print(f"Found {len(zombies)} zombies")
            for z in zombies:
                print(
                    f"- {z.resource_id} ({z.resource_type}): Estimated ${z.estimated_monthly_savings}/mo waste"
                )
        except Exception as e:
            print(f"Error checking zombies: {str(e)}")


if __name__ == "__main__":
    asyncio.run(check_zombies())
