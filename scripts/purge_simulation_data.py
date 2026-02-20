import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.shared.core.config import get_settings

async def purge_simulation_data_batched():
    """
    Purges all 'Scale Tenant' data in batches to avoid DB lock exhaustion.
    """
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if not db_url:
        print("DATABASE_URL not set.")
        return

    print(f"Purging simulation data from: {db_url.split('@')[-1]}")
    engine = create_async_engine(db_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Step 1: Count before
            res = await session.execute(text("SELECT count(*) FROM tenants WHERE name LIKE 'Scale Tenant %'"))
            tenant_count = res.scalar() or 0
            
            if tenant_count == 0:
                print("No simulation tenants found.")
                return

            print(f"Found {tenant_count} simulation tenants. Purging in batches...")

            # Get the list of tenant IDs to purge
            res = await session.execute(text("SELECT id FROM tenants WHERE name LIKE 'Scale Tenant %'"))
            tenant_ids = [str(r[0]) for r in res]
            tenant_ids_str = ",".join([f"'{tid}'" for tid in tenant_ids])

            # Batch DELETE for cost_records (the largest table)
            batch_size = 50000
            total_deleted = 0
            
            while True:
                # Use a direct delete with limit if possible, or filter by tenant_id
                # Postgres DELETE doesn't support LIMIT directly, so we use a subquery with LIMIT
                stmt = text(f"""
                    DELETE FROM cost_records 
                    WHERE id IN (
                        SELECT id FROM cost_records 
                        WHERE tenant_id IN ({tenant_ids_str})
                        LIMIT {batch_size}
                    )
                """)
                
                result = await session.execute(stmt)
                deleted_rows = result.rowcount
                await session.commit()
                
                if deleted_rows == 0:
                    break
                    
                total_deleted += deleted_rows
                print(f"  Deleted {total_deleted} cost_records...")
                # Small sleep to allow other TXs to breathe
                await asyncio.sleep(0.1)

            # Cloud Accounts
            await session.execute(text(f"DELETE FROM cloud_accounts WHERE tenant_id IN ({tenant_ids_str})"))
            
            # Users
            await session.execute(text(f"DELETE FROM users WHERE tenant_id IN ({tenant_ids_str})"))
            
            # Finally, the Tenants
            await session.execute(text(f"DELETE FROM tenants WHERE id IN ({tenant_ids_str})"))
            
            await session.commit()
            print("✅ Simulation data purged successfully.")
            
        except Exception as e:
            print(f"❌ PURGE ERROR: {e}")
            await session.rollback()
            sys.exit(1)
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(purge_simulation_data_batched())
