import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.shared.core.config import get_settings

async def cleanup_old_partitions():
    """
    Audits and drops cost_records partitions from 2025.
    """
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if not db_url:
        print("DATABASE_URL not set.")
        return

    engine = create_async_engine(db_url)
    
    try:
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            
            # List partitions
            res = await conn.execute(text("""
                SELECT child.relname AS partition_name 
                FROM pg_inherits 
                JOIN pg_class parent ON pg_inherits.inhparent = parent.oid 
                JOIN pg_class child ON pg_inherits.inhrelid = child.oid 
                WHERE parent.relname='cost_records' 
                AND child.relname LIKE 'cost_records_2025_%'
                ORDER BY partition_name;
            """))
            to_drop = [r[0] for r in res]
            
            if not to_drop:
                print("No 2025 partitions found.")
                return

            print(f"Found {len(to_drop)} partitions from 2025 to drop.")
            for part in to_drop:
                print(f"  Dropping {part}...")
                await conn.execute(text(f"DROP TABLE IF EXISTS {part} CASCADE;"))
            
            print("✅ 2025 partitions dropped successfully.")

    except Exception as e:
        print(f"❌ ERROR: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup_old_partitions())
