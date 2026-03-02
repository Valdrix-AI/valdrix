import asyncio
import sys
import os
from uuid import uuid4
from sqlalchemy import select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.shared.db.session import async_session_maker, engine
from app.models.tenant import Tenant, User, UserRole, UserPersona

async def seed_data():
    """Seed initial development data (Tenant + User)."""
    print("🌱 Seeding development data...", flush=True)

    async with async_session_maker() as db:
        async with db.begin():
            # Check for existing user (using simple limit query to avoid blind index complexity)
            res = await db.execute(select(User).limit(1))
            existing_user = res.scalars().first()
            
            if not existing_user:
                print("  + Creating initial Tenant and User...", flush=True)
                
                # Create Tenant
                tenant_id = uuid4()
                tenant = Tenant(
                    id=tenant_id,
                    name="Valdrics Dev",
                    plan="growth",
                    # trial_started_at=datetime.utcnow() 
                )
                db.add(tenant)
                
                # Create User
                user_id = uuid4()
                user = User(
                    id=user_id,
                    tenant_id=tenant_id,
                    email="admin@valdrics.com",
                    role=UserRole.OWNER.value,
                    persona=UserPersona.ENGINEERING.value,
                    is_active=True
                )
                db.add(user)
                
                print(f"  + Created Tenant: Valdrics Dev ({tenant_id})", flush=True)
                print(f"  + Created User: admin@valdrics.com ({user_id})", flush=True)
                print("  ! NOTE: Create this user in Supabase Auth with this UUID!", flush=True)
                print(f"  ! User ID: {user_id}", flush=True)
            else:
                 print("  ~ Users already exist, skipping seed.", flush=True)

    print("✅ Dev data seeding complete!", flush=True)
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
