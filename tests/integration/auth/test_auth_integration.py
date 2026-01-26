import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.auth import create_access_token
from app.models.aws_connection import AWSConnection
import uuid

@pytest.mark.asyncio
async def test_tenant_isolation(ac: AsyncClient, db: AsyncSession):
    """
    Verify that a user from Tenant A cannot access resources from Tenant B.
    """
    # 1. Setup Tenant A + Admin User
    tenant_a_id = uuid.uuid4()
    tenant_a = Tenant(id=tenant_a_id, name="Tenant A", plan="enterprise")
    db.add(tenant_a)
    
    user_a = User(
        id=uuid.uuid4(),
        email="admin@a.com", 
        tenant_id=tenant_a_id, 
        role=UserRole.ADMIN.value, 
        email_bidx="hash_a"
    )
    db.add(user_a)
    
    # 2. Setup Tenant B + Connection Resource
    tenant_b_id = uuid.uuid4()
    tenant_b = Tenant(id=tenant_b_id, name="Tenant B", plan="enterprise")
    db.add(tenant_b)
    
    conn_b_id = uuid.uuid4()
    conn_b = AWSConnection(
        id=conn_b_id, 
        tenant_id=tenant_b_id, 
        aws_account_id="123456789012", 
        role_arn="arn:aws:iam::123:role/role",
        external_id="ext_id"
    )
    db.add(conn_b)
    
    await db.commit()
    
    # 3. Login as Admin A
    token_a = create_access_token({
        "sub": str(user_a.id), 
        "tenant_id": str(tenant_a_id), 
        "role": UserRole.ADMIN.value
    })
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # 4. Attempt to List Connections (Should only see A's, so 0)
    response = await ac.get("/api/v1/settings/connections/aws", headers=headers_a)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert not any(c["id"] == str(conn_b_id) for c in data)
    
    # 5. Attempt to Delete B's Connection (Should be 404 Not Found due to RLS/filtering)
    # Most secure apps 404 resources they don't own rather than 403 to avoid enumeration
    response_del = await ac.delete(f"/api/v1/settings/connections/aws/{conn_b_id}", headers=headers_a)
    assert response_del.status_code == 404

@pytest.mark.asyncio
async def test_role_enforcement(ac: AsyncClient, db: AsyncSession):
    """
    Verify that a Member cannot perform Admin-only actions.
    """
    # 1. Setup Tenant + Member User
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, name="Tenant R", plan="enterprise")
    db.add(tenant)
    
    member = User(
        id=uuid.uuid4(),
        email="member@r.com", 
        tenant_id=tenant_id, 
        role=UserRole.MEMBER.value, 
        email_bidx="hash_r"
    )
    db.add(member)
    await db.commit()
    
    # 2. Login as Member
    token = create_access_token({
        "sub": str(member.id), 
        "tenant_id": str(tenant_id), 
        "role": UserRole.MEMBER.value
    })
    headers = {"Authorization": f"Bearer {token}"}
    
    # 3. Attempt Admin Action (Cancel Subscription)
    response = await ac.post("/api/v1/billing/cancel", headers=headers)
    assert response.status_code == 403
    error_msg = response.json().get("error", "") or response.json().get("message", "")
    assert "Insufficient permissions" in error_msg or "permissions" in error_msg.lower()
