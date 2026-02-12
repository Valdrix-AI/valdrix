import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, func
from app.models.cloud import CostRecord, CloudAccount
from app.schemas.costs import CloudUsageSummary, CostRecord as CostRecordSchema
from app.modules.reporting.domain.persistence import CostPersistenceService

@pytest.mark.asyncio
async def test_cost_persistence_idempotency(db):
    # 1. Setup - Create a tenant and account
    from app.models.tenant import Tenant
    tenant = Tenant(name="Test Tenant", plan="enterprise")
    db.add(tenant)
    await db.flush()
    
    account = CloudAccount(
        tenant_id=tenant.id,
        provider="aws",
        name="Test AWS",
        
    )
    db.add(account)
    await db.flush()

    service = CostPersistenceService(db)
    
    # 2. Prepare Sample Data (Fixed Date for Test Stability)
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    summary = CloudUsageSummary(
        tenant_id=str(tenant.id),
        provider="aws",
        start_date=now.date(),
        end_date=now.date(),
        total_cost=Decimal("100.00"),
        records=[
            CostRecordSchema(
                date=now,
                amount=Decimal("50.00"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage"
            ),
            CostRecordSchema(
                date=now,
                amount=Decimal("50.00"),
                service="AmazonS3",
                region="us-east-1",
                usage_type="Requests"
            )
        ]
    )

    # 3. First Ingestion
    await service.save_summary(summary, str(account.id))
    
    # Verify count for this account
    result = await db.execute(
        select(func.count())
        .select_from(CostRecord)
        .where(CostRecord.account_id == account.id)
    )
    count = result.scalar()
    assert count == 2

    # Verify canonical categories are populated during persistence
    result = await db.execute(
        select(CostRecord)
        .where(
            CostRecord.account_id == account.id,
            CostRecord.service == "AmazonEC2",
        )
    )
    ec2_record = result.scalar_one()
    assert ec2_record.canonical_charge_category == "compute"
    assert isinstance(ec2_record.ingestion_metadata, dict)
    assert (
        ec2_record.ingestion_metadata.get("canonical_mapping", {}).get("unmapped_reason")
        is None
    )

    result = await db.execute(
        select(CostRecord)
        .where(
            CostRecord.account_id == account.id,
            CostRecord.service == "AmazonS3",
        )
    )
    s3_record = result.scalar_one()
    assert s3_record.canonical_charge_category == "storage"
    assert isinstance(s3_record.ingestion_metadata, dict)
    assert (
        s3_record.ingestion_metadata.get("canonical_mapping", {}).get("unmapped_reason")
        is None
    )

    # 4. Second Ingestion (Same Data)
    await service.save_summary(summary, str(account.id))
    
    # Verify count is STILL 2 (Idempotency check)
    result = await db.execute(
        select(func.count())
        .select_from(CostRecord)
        .where(CostRecord.account_id == account.id)
    )
    count = result.scalar()
    assert count == 2

    # 5. Third Ingestion (Updated Data for same timestamp)
    summary.records[0].amount = Decimal("75.00")
    await service.save_summary(summary, str(account.id))
    
    # Verify count is still 2, but value is updated
    result = await db.execute(
        select(CostRecord)
        .where(
            CostRecord.account_id == account.id,
            CostRecord.service == "AmazonEC2"
        )
    )
    record = result.scalar_one()
    assert record.cost_usd == Decimal("75.00")
