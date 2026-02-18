import asyncio
import random
import time
from datetime import date, timedelta, datetime
from uuid import uuid4
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, func, select

# Import models
from app.models.cloud import CostRecord, CloudAccount
from app.models.tenant import Tenant, User
from app.shared.core.config import get_settings

async def seed_scale_data(engine, num_tenants=10, records_per_tenant=100000):
    """Seed a massive amount of cost records to test index performance."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Cleanup existing scale data
        print("Cleaning up old scale data...")
        await session.execute(text("DELETE FROM cost_records WHERE tenant_id IN (SELECT id FROM tenants WHERE name LIKE 'Scale Tenant %')"))
        await session.execute(text("DELETE FROM cloud_accounts WHERE tenant_id IN (SELECT id FROM tenants WHERE name LIKE 'Scale Tenant %')"))
        await session.execute(text("DELETE FROM tenants WHERE name LIKE 'Scale Tenant %'"))
        await session.commit()

        # 1. Create Tenants
        print(f"Creating {num_tenants} tenants...")
        tenants = []
        for i in range(num_tenants):
            t = Tenant(id=uuid4(), name=f"Scale Tenant {i}")
            session.add(t)
            tenants.append(t)
        
        await session.commit()
        
        # 2. Create Cloud Accounts
        print("Creating cloud accounts...")
        accounts = []
        for t in tenants:
            acc = CloudAccount(
                id=uuid4(),
                tenant_id=t.id,
                provider="aws",
                name=f"AWS Main - {t.name}",
                is_active=True
            )
            session.add(acc)
            accounts.append(acc)
        
        await session.commit()
        
        # 3. Bulk Insert Cost Records
        from sqlalchemy import insert
        print(f"Seeding {num_tenants * records_per_tenant} records using bulk insert...")
        services = ["EC2", "S3", "RDS", "Lambda", "DynamoDB"]
        
        batch_size = 20000
        total_seeded = 0
        
        for acc in accounts:
            batch = []
            start_date = date.today() - timedelta(days=365)
            
            for i in range(records_per_tenant):
                usage_date = start_date + timedelta(days=random.randint(0, 364))
                batch.append({
                    "id": uuid4(),
                    "tenant_id": acc.tenant_id,
                    "account_id": acc.id,
                    "service": random.choice(services),
                    "recorded_at": usage_date,
                    "cost_usd": Decimal(str(round(random.uniform(0.01, 50.0), 2))),
                    "currency": "USD",
                    "usage_amount": Decimal(str(round(random.uniform(0.1, 100.0), 4))),
                    "usage_unit": "Hrs",
                    "region": "us-east-1"
                })
                
                if len(batch) >= batch_size:
                    await session.execute(insert(CostRecord), batch)
                    await session.commit()
                    total_seeded += len(batch)
                    print(f"Progress: {total_seeded} records seeded...")
                    batch = []
            
            if batch:
                await session.execute(insert(CostRecord), batch)
                await session.commit()
                total_seeded += len(batch)
                print(f"Progress: {total_seeded} records seeded...")

async def run_benchmark(engine, tenant_id):
    """Run performance benchmarks on the seeded data."""
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    queries = [
        ("Simple Sum", select(func.sum(CostRecord.cost_usd)).where(CostRecord.tenant_id == tenant_id)),
        ("Range Aggregation", select(func.sum(CostRecord.cost_usd)).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= date.today() - timedelta(days=90)
        )),
        ("Group by Service", select(CostRecord.service, func.sum(CostRecord.cost_usd)).where(
            CostRecord.tenant_id == tenant_id
        ).group_by(CostRecord.service))
    ]
    
    print("\n--- PERFORMANCE BENCHMARKS ---")
    async with async_session() as session:
        for label, stmt in queries:
            print(f"Running: {label}...")
            
            # Use EXPLAIN ANALYZE
            explain_stmt = text(f"EXPLAIN ANALYZE {str(stmt.compile(engine, compile_kwargs={'literal_binds': True}))}")
            
            start = time.perf_counter()
            result = await session.execute(explain_stmt)
            end = time.perf_counter()
            
            print(f"Time: {(end - start) * 1000:.2f}ms")
            for row in result:
                print(f"  {row[0]}")
            print("-" * 30)

async def main():
    settings = get_settings()
    db_url = settings.DATABASE_URL
    if "sqlite" in db_url:
        print("Benchmarking on SQLite is not representative for Phase 3 scaling. Please run against PostgreSQL.")
        return

    engine = create_async_engine(db_url)
    
    # Run seeding (optional, if db is empty)
    # try:
    #     # 10 tenants x 100,000 records = 1,000,000 total
    #     await seed_scale_data(engine, num_tenants=10, records_per_tenant=100000)
    # except Exception as e:
    #     print(f"SEEDING ERROR: {e}")
    #     # Continue to benchmark if possible
    
    # Get a random tenant
    async_session = async_sessionmaker(engine)
    async with async_session() as session:
        tenant_id = await session.scalar(select(Tenant.id).where(Tenant.name.like("Scale Tenant %")))
        if not tenant_id:
            print("No scale tenants found. Attempting with any tenant...")
            tenant_id = await session.scalar(select(Tenant.id))
        
        if not tenant_id:
            print("No tenants found at all.")
            return
        
        await run_benchmark(engine, tenant_id)

if __name__ == "__main__":
    asyncio.run(main())
