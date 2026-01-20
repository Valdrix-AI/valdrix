import asyncio
from sqlalchemy import text
from app.db.session import async_session_maker

async def check():
    try:
        async with async_session_maker() as db:
            # Check if audit_logs exists
            res = await db.execute(text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'audit_logs')"))
            exists = res.scalar()
            print(f"Table 'audit_logs' exists: {exists}")
            
            if exists:
                res = await db.execute(text("""
                    SELECT nmsp_parent.nspname AS parent_schema,
                           rel_parent.relname AS parent_table,
                           nmsp_child.nspname AS child_schema,
                           rel_child.relname AS child_table
                    FROM pg_inherits
                    JOIN pg_class rel_parent ON pg_inherits.inhparent = rel_parent.oid
                    JOIN pg_class rel_child ON pg_inherits.inhrelid = rel_child.oid
                    JOIN pg_namespace nmsp_parent ON rel_parent.relnamespace = nmsp_parent.oid
                    JOIN pg_namespace nmsp_child ON rel_child.relnamespace = nmsp_child.oid
                    WHERE rel_parent.relname = 'audit_logs';
                """))
                partitions = res.fetchall()
                if not partitions:
                    print("No partitions found for audit_logs")
                else:
                    print(f"Found {len(partitions)} partitions:")
                    for p in partitions:
                        print(f" - {p.child_table}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(check())
