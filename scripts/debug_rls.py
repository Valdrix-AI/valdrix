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
        # Check table schema and owner
        res = await conn.execute(text("""
            SELECT schemaname, tablename, tableowner, rowsecurity 
            FROM pg_tables 
            WHERE tablename IN ('tenants', 'aws_connections', 'users')
        """))
        for row in res.fetchall():
            print(f"Table: {row.schemaname}.{row.tablename}, Owner: {row.tableowner}, RLS: {row.rowsecurity}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
