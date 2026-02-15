import asyncio
from app.shared.db.session import async_session_maker
from sqlalchemy import text


async def check_tables():
    async with async_session_maker() as session:
        # Check all tables
        result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        )
        tables = [row[0] for row in result.all()]
        print(f"Tables found: {tables}")

        # Check specific table
        has_subscriptions = "tenant_subscriptions" in tables
        print(f"tenant_subscriptions exists: {has_subscriptions}")

        # Check llm_usage
        has_llm_usage = "llm_usage" in tables
        print(f"llm_usage exists: {has_llm_usage}")


if __name__ == "__main__":
    asyncio.run(check_tables())
