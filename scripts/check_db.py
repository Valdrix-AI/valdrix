import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_db():
    engine = create_async_engine('postgresql+asyncpg://postgres.ouflnjgsyfqqvjqlpcic:GgIFxzzGu19LUPZM@aws-1-us-east-1.pooler.supabase.com:5432/postgres')
    async with engine.connect() as conn:
        count = await conn.scalar(text('SELECT count(*) FROM cost_records'))
        print(f'Current cost_records: {count}')
        
        # Check if partitioned
        res = await conn.execute(text("SELECT relkind FROM pg_class WHERE relname = 'cost_records'"))
        row = res.fetchone()
        if row:
            print(f"Table kind: {row[0]} (p=partitioned, r=regular)")
            
        # List partitions if any
        res = await conn.execute(text("SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent = 'cost_records'::regclass"))
        partitions = res.fetchall()
        print(f"Partitions: {[str(p[0]) for p in partitions]}")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_db())
