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
        # Check current version
        version_res = await conn.execute(text("SELECT version_num FROM alembic_version"))
        versions = [r[0] for r in version_res.fetchall()]
        print(f"Alembic Versions: {versions}")
        
        # Check RLS status of sensitive tables
        tables = [
            "aws_connections",
            "azure_connections",
            "gcp_connections",
            "cost_records",
            "remediation_requests",
            "users",
            "tenants",
            "background_jobs"
        ]
        
        for table in tables:
            res = await conn.execute(text(f"SELECT rowsecurity FROM pg_tables WHERE tablename = '{table}'"))
            row = res.fetchone()
            rls_enabled = row[0] if row else "NOT FOUND"
            print(f"Table {table}: RLS Enabled = {rls_enabled}")
            
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
