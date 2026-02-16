import asyncio
from app.shared.db.session import async_session_maker

import time

async def run_optimization():
    print("⚡ Starting Database Performance & Security Hardening...")
    start_total = time.time()
    
    with open('scripts/optimize_performance_and_security.sql', 'r') as f:
        sql = f.read()
    
    async with async_session_maker() as db:
        try:
            # Get the underlying asyncpg connection
            conn = await db.connection()
            raw_conn = await conn.get_raw_connection()
            
            # Execute the entire script as one multi-statement string
            # We use the internal driver connection to support this directly
            await raw_conn.driver_connection.execute(sql)
            
            print(f"🏁 Total hardening time: {time.time() - start_total:.2f}s")
            print("✅ Database Performance & Security Hardening applied successfully!")
        except Exception as e:
            # The transaction is handled by the SQL script itself (BEGIN/COMMIT)
            # but we should still log the error properly.
            print(f"❌ Error during hardening: {e}")
            raise

if __name__ == "__main__":
    asyncio.run(run_optimization())
