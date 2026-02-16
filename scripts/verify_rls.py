import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.shared.core.config import get_settings

async def check():
    engine = create_async_engine(
        get_settings().DATABASE_URL,
        connect_args={"statement_cache_size": 0}
    )
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = true"))
        rls_tables = [r[0] for r in result.fetchall()]
        print(f"RLS Enabled Tables: {rls_tables}")
        
        all_tables_result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        all_tables = [r[0] for r in all_tables_result.fetchall()]
        
        missing_rls = [t for t in all_tables if t not in rls_tables and t not in ["alembic_version"]]
        if missing_rls:
            print(f"WARNING: No RLS on: {missing_rls}")
        else:
            print("SUCCESS: All application tables have RLS enabled.")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
