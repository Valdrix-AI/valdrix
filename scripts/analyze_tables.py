import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.shared.core.config import get_settings

async def analyze_inventory():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as conn:
        # Get all tables
        res = await conn.execute(text("""
            SELECT 
                relname as name,
                pg_size_pretty(pg_total_relation_size(c.oid)) as size,
                relrowsecurity as rls
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND relkind = 'r' AND relname NOT LIKE 'alembic_%'
            ORDER BY name;
        """))
        all_tables = res.fetchall()
        
        partitions = [t.name for t in all_tables if any(x in t.name for x in ["_2026", "_2027", "_p2026", "_p2027"])]
        base_tables = [t.name for t in all_tables if t.name not in partitions]
        
        print("\nDB Inventory Analysis:")
        print(f"Total entries: {len(all_tables)}")
        print(f"Base Tables ({len(base_tables)}):")
        for t in sorted(base_tables):
            print(f"  - {t}")
            
        print(f"\nPartitions ({len(partitions)}):")
        # Group partitions by parent
        parents = {}
        for p in partitions:
            if "cost_records" in p: parents.setdefault("cost_records", []).append(p)
            elif "audit_logs" in p: parents.setdefault("audit_logs", []).append(p)
            else: parents.setdefault("other", []).append(p)
            
        for parent, children in parents.items():
            print(f"  - {parent}: {len(children)} partitions")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(analyze_inventory())
