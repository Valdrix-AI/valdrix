
import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def wipe_database():
    """Drops all tables, views, and types in the public schema."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in environment.")
        return

    # Extract connection parameters from URL or use it directly
    # asyncpg expects a DSN or individual params
    
    print("Connecting to database to perform wipe...")
    # Fix scheme for asyncpg if it's using sqlalchemy+asyncpg format
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # 1. Drop all tables in public schema
        print("Dropping all tables in public schema...")
        await conn.execute("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                END LOOP;
            END $$;
        """)

        # 2. Drop all custom types/enums
        print("Dropping all custom types in public schema...")
        await conn.execute("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public' AND t.typtype = 'e') LOOP
                    EXECUTE 'DROP TYPE IF EXISTS ' || quote_ident(r.typname) || ' CASCADE';
                END LOOP;
            END $$;
        """)

        # 3. Drop all functions
        print("Dropping all functions in public schema...")
        await conn.execute("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public') LOOP
                    EXECUTE 'DROP FUNCTION IF EXISTS ' || quote_ident(r.routine_name) || ' CASCADE';
                END LOOP;
            END $$;
        """)

        print("✅ Database wipe complete. Public schema is now empty.")

    except Exception as e:
        print(f"❌ Error during wipe: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(wipe_database())
