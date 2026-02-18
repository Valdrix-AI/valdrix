import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.shared.core.config import get_settings

async def check():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        res = await conn.execute(text("""
            SELECT relname, relrowsecurity 
            FROM pg_class 
            WHERE relname IN ('cost_records_2026_01', 'audit_logs_p2026_01', 'tenant_subscriptions', 'attribution_rules')
        """))
        for r in res:
            print(f"TABLE: {r[0]} | RLS: {r[1]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
