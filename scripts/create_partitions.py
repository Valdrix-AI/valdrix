import asyncio
from sqlalchemy import text
from app.shared.db.session import async_session_maker
from datetime import date
from dateutil.relativedelta import relativedelta

async def create_partitions():
    session = async_session_maker()
    today = date.today()
    # Create partitions for past 12 months and next 12 months
    for i in range(-12, 13):
        target = today + relativedelta(months=i)
        p_name = f"cost_records_{target.year}_{target.month:02d}"
        start = date(target.year, target.month, 1)
        end = start + relativedelta(months=1)
        
        sql = text(f"""
            CREATE TABLE IF NOT EXISTS {p_name} 
            PARTITION OF cost_records 
            FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
        """)
        print(f"Creating partition {p_name}...")
        try:
            await session.execute(sql)
            await session.commit()
        except Exception as e:
            print(f"Failed to create {p_name}: {e}")
            await session.rollback()
            
    await session.close()

if __name__ == "__main__":
    asyncio.run(create_partitions())
