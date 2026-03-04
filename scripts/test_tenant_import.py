import asyncio
import sys
import os
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.shared.db.session import async_session_maker, engine
from app.models.tenant import Tenant, User, UserRole, UserPersona

async def seed_data():
    print("🌱 Seeding test...", flush=True)
    async with async_session_maker() as db:
        async with db.begin():
            print("✅ Session created!", flush=True)
            
            # Check User query with raw SQL
            print("🔍 Checking User query (RAW)...", flush=True)
            res = await db.execute(text("SELECT id FROM users LIMIT 1"))
            print(f"✅ RAW User Query executed! Count: {len(res.all())}", flush=True)

            # Check User query with ORM
            print("🔍 Checking User query (ORM)...", flush=True)
            try:
                res = await db.execute(select(User).limit(1))
                print(f"✅ ORM User Query executed! Count: {len(res.scalars().all())}", flush=True)
            except (SQLAlchemyError, OSError, RuntimeError, TypeError, ValueError) as e:
                print(f"❌ ORM Failed: {e}", flush=True)
            
            # Try insert Tenant
            print("🌱 Inserting Tenant...", flush=True)
            tenant_id = uuid4() 
            t = Tenant(id=tenant_id, name="Test Tenant", plan="growth")
            db.add(t)
            print("✅ Tenant Added!", flush=True)
            
            # Try insert User
            print("🌱 Inserting User...", flush=True)
            user_id = uuid4()
            u = User(
                id=user_id,
                tenant_id=tenant_id,
                email="admin@valdrics.com",
                role=UserRole.OWNER.value,
                persona=UserPersona.ENGINEERING.value,
                is_active=True
            )
            db.add(u)
            print("✅ User Added!", flush=True)

        print("✅ Commit successful!", flush=True)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
