import pytest
from uuid import uuid4
from datetime import date
from unittest.mock import AsyncMock, patch
from decimal import Decimal

from app.shared.adapters.gcp import GCPAdapter
from app.modules.reporting.domain.attribution_engine import AttributionEngine
from app.models.cloud import CostRecord

@pytest.mark.asyncio
async def test_gcp_multi_credit_extraction(db_session):
    """
    Verify that GCPAdapter correctly sums all credit types.
    """
    # Mock row with multiple credits
    mock_row = AsyncMock()
    mock_row.timestamp = date.today()
    mock_row.service = "Compute Engine"
    mock_row.cost_usd = 100.0
    mock_row.total_credits = -25.0 # SUD + CUD
    mock_row.currency = "USD"
    
    mock_results = [mock_row]
    
    with patch("google.cloud.bigquery.Client") as mock_bq:
        mock_bq.return_value.query.return_value.result.return_value = mock_results
        
        from app.models.gcp_connection import GCPConnection
        conn = GCPConnection(
            project_id="test-project",
            billing_dataset="dataset",
            billing_table="table"
        )
        adapter = GCPAdapter(conn)
        
        records = await adapter.get_cost_and_usage(date.today(), date.today())
        
        assert len(records) == 1
        assert records[0]["amortized_cost"] == 75.0
        assert records[0]["credits"] == -25.0

@pytest.mark.asyncio
async def test_untagged_recommendations(db_session):
    """
    Verify that AttributionEngine identifies top unallocated services.
    """
    from app.models.tenant import Tenant
    from app.models.cloud import CloudAccount
    
    tenant_id = uuid4()
    account_id = uuid4()
    
    # Setup: Create tenant and cloud account
    tenant = Tenant(id=tenant_id, name="Test Tenant")
    db_session.add(tenant)
    await db_session.commit()
    
    cloud_account = CloudAccount(
        id=account_id,
        tenant_id=tenant_id,
        provider="gcp",
        name="Test Project",
        is_active=True
    )
    db_session.add(cloud_account)
    await db_session.commit()
    
    # Create unallocated records
    records = [
        CostRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            service="Compute Engine",
            cost_usd=Decimal("500.00"),
            recorded_at=date.today(),
            allocated_to="Unallocated",
            account_id=account_id
        ),
        CostRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            service="Cloud Storage",
            cost_usd=Decimal("100.00"),
            recorded_at=date.today(),
            allocated_to="Unallocated",
            account_id=account_id
        )
    ]
    db_session.add_all(records)
    await db_session.commit()
    
    engine = AttributionEngine(db_session)
    analysis = await engine.get_unallocated_analysis(tenant_id, date.today(), date.today())
    
    assert len(analysis) >= 2
    assert analysis[0]["service"] == "Compute Engine"
    assert "Create a DIRECT rule" in analysis[0]["recommendation"]

