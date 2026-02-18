import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.shared.core.config import get_settings

async def truncate_cost_data():
    """
    Definitively empties the cost_records table using TRUNCATE CASCADE.
    This is the fastest way to reclaim storage in physical partitions.
    """
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if not db_url:
        print("DATABASE_URL not set.")
        return

    print(f"TRUNCATING cost_records on: {db_url.split('@')[-1]}")
    engine = create_async_engine(db_url)
    
    try:
        async with engine.connect() as conn:
            # Set isolation level to AUTOCOMMIT for TRUNCATE/VACUUM if needed,
            # though TRUNCATE works in TX, it's safer to ensure it commits immediately.
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            
            print("Executing TRUNCATE cost_records CASCADE...")
            await conn.execute(text("TRUNCATE TABLE cost_records CASCADE;"))
            print("✅ Table truncated successfully.")
            
            print("Executing VACUUM ANALYZE to update statistics...")
            await conn.execute(text("VACUUM ANALYZE;"))
            print("✅ Vacuum completed.")

            # Final size check
            res = await conn.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;
            """))
            print(f"Final DB Size: {res.scalar()}")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(truncate_cost_data())
