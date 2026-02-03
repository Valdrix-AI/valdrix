import asyncio
from uuid import uuid4
from sqlalchemy import select
from app.shared.db.session import async_session_maker
from app.models.remediation import RemediationRequest, RemediationAction
# Import all models to ensure SQLAlchemy mappers are initialized

from app.models.tenant import Tenant, User
from app.modules.optimization.domain import RemediationService

async def verify_active_ops():
    print("🚀 Starting ActiveOps Dry-Run Verification...")
    
    async with async_session_maker() as db:
        # 1. Ensure a tenant exists
        print("🏢 Ensuring test tenant exists...")
        result = await db.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            tenant = Tenant(name="E2E Test Tenant", plan="pro")
            db.add(tenant)
            await db.flush()
            print(f"✨ Created test tenant: {tenant.id}")
        else:
            print(f"✅ Using existing tenant: {tenant.id}")
            
        tenant_id = tenant.id
        
        # 2. Ensure a user exists for this tenant
        result = await db.execute(select(User).where(User.tenant_id == tenant_id).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(id=uuid4(), tenant_id=tenant_id, email="e2e@example.com", role="admin")
            db.add(user)
            await db.flush()
            print(f"✨ Created test user: {user.id}")
        else:
            print(f"✅ Using existing user: {user.id}")
            
        user_id = user.id
        
        # 3. Simulate finding a zombie
        print("🔍 Creating remediation request...")
        # We manually create a request to bypass provider connection for dry-run
        rem_service = RemediationService(db=db, region="us-east-1")
        
        req = await rem_service.create_request(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_id="i-e2e-12345",
            resource_type="ec2_instance",
            action=RemediationAction.TERMINATE_INSTANCE,
            estimated_savings=15.75,
            provider="aws"
        )
        
        await db.commit()
        print(f"✅ Created remediation request: {req.id}")
        
        # 4. Verify in DB
        result = await db.execute(select(RemediationRequest).where(RemediationRequest.id == req.id))
        persisted = result.scalar_one_or_none()
        
        assert persisted is not None
        assert persisted.status.value == "pending"
        
        print(f"📊 Verified status: {persisted.status.value}")
        print("🏆 ActiveOps Verification PASSED.")


if __name__ == "__main__":
    asyncio.run(verify_active_ops())
