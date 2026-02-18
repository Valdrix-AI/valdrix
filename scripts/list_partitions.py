import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.shared.core.config import get_settings

async def list_partitions():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        print("\n--- Partition Audit ---")
        for table in ["cost_records", "audit_logs"]:
            print(f"\nTable: {table}")
            res = await conn.execute(text(f"""
                SELECT child.relname AS partition_name 
                FROM pg_inherits 
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid 
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid 
                WHERE parent.relname='{table}' 
                ORDER BY partition_name;
            """))
            for r in res:
                print(f"  {r.partition_name}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(list_partitions())
