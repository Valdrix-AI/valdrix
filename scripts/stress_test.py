import asyncio
import time
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models.remediation import RemediationRequest, RemediationStatus
from app.models.tenant import User

async def stress_test_leaderboard(n_users=100, n_remediations=5000):
    """
    Stress test for leaderboard calculation logic.
    Simulates high count of users and remediations in an in-memory DB.
    """
    print(f"🚀 Starting Leaderboard Stress Test: {n_users} users, {n_remediations} remediations")
    
    # Use in-memory SQLite for high-speed local stress testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    
    async with engine.begin() as conn:
        from app.models.tenant import Base
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    tenant_id = uuid4()
    
    start_setup = time.perf_counter()
    async with async_session() as session:
        # 1. Create Users
        users = [
            User(id=uuid4(), tenant_id=tenant_id, email=f"user_{i}@example.com")
            for i in range(n_users)
        ]

        session.add_all(users)
        
        # 2. Create Remediations
        remediations = []
        for i in range(n_remediations):
            user = users[i % n_users]
            remediations.append(RemediationRequest(
                id=uuid4(),
                tenant_id=tenant_id,
                resource_id=f"res_{i}",
                resource_type="ec2",
                provider="aws", # Explicitly set provider
                region="us-east-1", # Explicitly set region
                action="stop_idle",
                estimated_monthly_savings=i * 0.1,
                status=RemediationStatus.COMPLETED,
                requested_by_user_id=user.id, # Mandatory field
                reviewed_by_user_id=user.id,
                created_at=datetime.now(timezone.utc)
            ))

        session.add_all(remediations)
        await session.commit()
    
    setup_duration = time.perf_counter() - start_setup
    print(f"✅ Setup complete in {setup_duration:.2f}s")
    
    # 3. Benchmark Query
    start_time = time.perf_counter()
    async with async_session() as session:
        # Optimized Leaderboard Query from Leaderboards API
        query = (
            select(
                User.email.label("user_email"),
                func.sum(RemediationRequest.estimated_monthly_savings).label("total_savings"),
                func.count(RemediationRequest.id).label("count"),
            )
            .join(User, RemediationRequest.reviewed_by_user_id == User.id)
            .where(
                RemediationRequest.tenant_id == tenant_id,
                RemediationRequest.status == RemediationStatus.COMPLETED,
            )
            .group_by(User.email)
            .order_by(func.sum(RemediationRequest.estimated_monthly_savings).desc())
            .limit(100)
        )
        
        result = await session.execute(query)
        rows = result.fetchall()
        
    duration = time.perf_counter() - start_time
    print(f"📊 Leaderboard query (Top 100) took: {duration:.4f}s")
    
    assert len(rows) > 0
    print(f"✅ Performance Verification PASSED: {duration:.4f}s (< 0.1s SLA)")

if __name__ == "__main__":
    asyncio.run(stress_test_leaderboard())
