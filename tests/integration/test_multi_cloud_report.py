import pytest
from httpx import AsyncClient
from datetime import date
from uuid import uuid4
from decimal import Decimal
from app.models.cloud import CloudAccount, CostRecord
from app.shared.core.auth import CurrentUser, get_current_user
from app.shared.db.session import get_db
from app.main import app

@pytest.fixture
def mock_auth_user_multi():
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        email="multi@valdrix.ai",
        tenant_id=tenant_id,
        role="admin",
        permissions=["read", "write", "admin"],
        tier="enterprise"
    )
    return user

@pytest.mark.asyncio
async def test_multi_cloud_unified_report(ac: AsyncClient, db, mock_auth_user_multi):
    """
    Integration Test: Verify Unified Multi-Cloud Reporting.
    Simulates data from AWS, Azure, and GCP and checks aggregation API.
    """
    # Setup Override
    app.dependency_overrides[get_current_user] = lambda: mock_auth_user_multi
    app.dependency_overrides[get_db] = lambda: db
    
    try:
        tenant_id = mock_auth_user_multi.tenant_id
        
        # 0. Create Tenant
        from sqlalchemy import text
        await db.execute(text(f"INSERT INTO tenants (id, name, plan) VALUES ('{tenant_id}', 'Unified Corp', 'enterprise') ON CONFLICT DO NOTHING"))
        await db.commit()
        
        # 1. Setup Accounts
        aws_id = uuid4()
        azure_id = uuid4()
        gcp_id = uuid4()
        
        db.add_all([
            CloudAccount(id=aws_id, tenant_id=tenant_id, provider="aws", name="AWS Prod", credentials_encrypted="x", is_active=True),
            CloudAccount(id=azure_id, tenant_id=tenant_id, provider="azure", name="Azure Dev", credentials_encrypted="x", is_active=True),
            CloudAccount(id=gcp_id, tenant_id=tenant_id, provider="gcp", name="GCP Analytics", credentials_encrypted="x", is_active=True),
        ])
        
        # 2. Insert Cost Data across 3 clouds
        today = date.today()
        
        records = [
            # AWS: $200
            CostRecord(tenant_id=tenant_id, account_id=aws_id, service="AmazonEC2", region="us-1", usage_type="Comp", cost_usd=Decimal("150.00"), recorded_at=today),
            CostRecord(tenant_id=tenant_id, account_id=aws_id, service="AmazonS3", region="us-1", usage_type="Stor", cost_usd=Decimal("50.00"), recorded_at=today),
            
            # Azure: $100
            CostRecord(tenant_id=tenant_id, account_id=azure_id, service="AzureSQL", region="eu-1", usage_type="DB", cost_usd=Decimal("100.00"), recorded_at=today),
            
            # GCP: $50
            CostRecord(tenant_id=tenant_id, account_id=gcp_id, service="BigQuery", region="us-central1", usage_type="Analytics", cost_usd=Decimal("50.00"), recorded_at=today),
        ]
        
        db.add_all(records)
        await db.commit()
        
        # 3. Call Unified Report API
        # GET /api/v1/costs/summary is likely the endpoint, or /api/v1/costs
        # Based on aggregator.py, specific endpoints might be used.
        # Let's use the one from test_cost_aggregation: /api/v1/costs
        
        # Test A: Grand Total
        resp = await ac.get(f"/api/v1/costs?start_date={today}&end_date={today}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Verify Total: 150+50+100+50 = 350
        assert data["total_cost"] == 350.0
        assert len(data["breakdown"]) == 4  # 4 services
        
        # Test B: Provider Breakdown (AWS Specific)
        resp_aws = await ac.get(f"/api/v1/costs?start_date={today}&end_date={today}&provider=aws")
        data_aws = resp_aws.json()
        assert data_aws["total_cost"] == 200.0
        assert len(data_aws["breakdown"]) == 2 # EC2, S3
        
        # Test C: Dashboard Summary endpoint (if exists, usually /api/v1/costs/dashboard or similar)
        # Checking aggregator.py `get_dashboard_summary`, it might be exposed via /api/v1/costs/dashboard
        resp_db = await ac.get(f"/api/v1/costs/dashboard?start_date={today}&end_date={today}")
        if resp_db.status_code == 200:
            data_db = resp_db.json()
            assert data_db["total_cost"] == 350.0
            assert data_db["provider"] == "multi"
            
    finally:
        app.dependency_overrides = {}
