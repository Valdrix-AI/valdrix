import pytest
import jwt
import json
import hmac
import hashlib
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
import respx
from sqlalchemy import select
from app.shared.core.config import get_settings
from app.models.tenant import Tenant, User, UserRole
from app.shared.core.pricing import PricingTier
from app.modules.reporting.domain.billing.paystack_billing import TenantSubscription, SubscriptionStatus

settings = get_settings()

def create_test_token(user_id: UUID, email: str):
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated", # Match Supabase default aud
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    }
    return jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

def generate_paystack_signature(payload: bytes, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        payload,
        hashlib.sha512
    ).hexdigest()

@pytest.fixture(autouse=True)
async def cleanup_overrides():
    from app.main import app
    from app.shared.db.session import get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.fixture
async def test_data(db):
    tenant = Tenant(id=uuid4(), name="Test Tenant", plan=PricingTier.STARTER.value)
    user = User(
        id=uuid4(),
        tenant_id=tenant.id,
        email="test@example.com",
        role=UserRole.ADMIN
    )
    db.add(tenant)
    db.add(user)
    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)
    
    token = create_test_token(user.id, user.email)
    return {"tenant": tenant, "user": user, "token": token}

@respx.mock
@pytest.mark.anyio
async def test_create_checkout_success(ac: AsyncClient, test_data, db):
    """Verify checkout session creation with dynamic exchange rate conversion."""
    # 1. Mock Exchange Rate API
    respx.get(url__startswith="https://v6.exchangerate-api.com/v6").respond(
        json={
            "result": "success",
            "conversion_rates": {"NGN": 1500.0}
        }
    )
    
    # 2. Mock Paystack Initialize Transaction
    respx.post("https://api.paystack.co/transaction/initialize").respond(
        json={
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/test_token",
                "reference": "test_ref_123"
            }
        }
    )
    
    headers = {"Authorization": f"Bearer {test_data['token']}"}
    payload = {
        "tier": "growth",
        "billing_cycle": "monthly"
    }
    
    response = await ac.post("/api/v1/billing/checkout", json=payload, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://checkout.paystack.com/test_token"
    assert data["reference"] == "test_ref_123"

@respx.mock
@pytest.mark.anyio
async def test_webhook_charge_success_activates_subscription(ac: AsyncClient, test_data, db):
    """Verify that a successful charge webhook activates the tenant's subscription."""
    
    webhook_payload = {
        "event": "charge.success",
        "data": {
            "reference": "test_ref_123",
            "status": "success",
            "amount": 290000,
            "metadata": {
                "tenant_id": str(test_data["tenant"].id),
                "tier": "growth"
            },
            "customer": {
                "customer_code": "CUS_test_001",
                "email": "test@example.com"
            },
            "authorization": {
                "authorization_code": "AUTH_test_999",
                "card_type": "visa"
            },
            "plan": {
                "name": "Growth Plan",
                "plan_code": "PLN_growth_xxx"
            }
        }
    }
    
    SECRET = "test_paystack_secret_123"
    payload_bytes = json.dumps(webhook_payload).encode()
    signature = generate_paystack_signature(payload_bytes, SECRET)
    
    # Temporarily ensure secret key is set for test
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.modules.reporting.domain.billing.paystack_billing.settings.PAYSTACK_SECRET_KEY", SECRET)
        
        headers = {"x-paystack-signature": signature}
        response = await ac.post("/api/v1/billing/webhook", content=payload_bytes, headers=headers)
        
        assert response.status_code == 200
        
        # Verify DB state
        result = await db.execute(
            select(TenantSubscription).where(TenantSubscription.tenant_id == test_data["tenant"].id)
        )
        subscription = result.scalar_one_or_none()
        
        assert subscription is not None
        assert subscription.status == SubscriptionStatus.ACTIVE.value
        assert subscription.tier == "growth"
        assert subscription.paystack_customer_code == "CUS_test_001"
        assert subscription.paystack_auth_code is not None # Should be encrypted

@pytest.mark.anyio
async def test_webhook_invalid_signature_rejection(ac: AsyncClient):
    """Security: Webhooks with invalid signatures must be rejected."""
    payload = {"event": "charge.success"}
    headers = {"x-paystack-signature": "invalid_signature"}
    
    response = await ac.post("/api/v1/billing/webhook", json=payload, headers=headers)
    assert response.status_code == 401
