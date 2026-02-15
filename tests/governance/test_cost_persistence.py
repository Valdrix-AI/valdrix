import pytest
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, func
from app.models.cloud import CostRecord, CloudAccount
from app.schemas.costs import CloudUsageSummary, CostRecord as CostRecordSchema
from app.modules.reporting.domain.persistence import CostPersistenceService
from uuid import uuid4


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
                usage_type="BoxUsage",
            ),
            CostRecordSchema(
                date=now,
                amount=Decimal("50.00"),
                service="AmazonS3",
                region="us-east-1",
                usage_type="Requests",
            ),
        ],
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
        select(CostRecord).where(
            CostRecord.account_id == account.id,
            CostRecord.service == "AmazonEC2",
        )
    )
    ec2_record = result.scalar_one()
    assert ec2_record.canonical_charge_category == "compute"
    assert isinstance(ec2_record.ingestion_metadata, dict)
    assert (
        ec2_record.ingestion_metadata.get("canonical_mapping", {}).get(
            "unmapped_reason"
        )
        is None
    )

    result = await db.execute(
        select(CostRecord).where(
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
        select(CostRecord).where(
            CostRecord.account_id == account.id, CostRecord.service == "AmazonEC2"
        )
    )
    record = result.scalar_one()
    assert record.cost_usd == Decimal("75.00")


@pytest.mark.asyncio
async def test_stream_ingestion_preserves_final_and_audits_restatements(db):
    from app.models.tenant import Tenant
    from app.models.cost_audit import CostAuditLog

    tenant = Tenant(name="Restatement Tenant", plan="enterprise")
    db.add(tenant)
    await db.flush()

    account = CloudAccount(tenant_id=tenant.id, provider="aws", name="AWS Ledger")
    db.add(account)
    await db.flush()

    service = CostPersistenceService(db)
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    summary = CloudUsageSummary(
        tenant_id=str(tenant.id),
        provider="aws",
        start_date=now.date(),
        end_date=now.date(),
        total_cost=Decimal("50.00"),
        records=[
            CostRecordSchema(
                date=now,
                amount=Decimal("50.00"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage",
            )
        ],
    )

    await service.save_summary(
        summary,
        str(account.id),
        reconciliation_run_id=uuid4(),
        is_preliminary=False,
    )

    record = await db.scalar(
        select(CostRecord).where(
            CostRecord.account_id == account.id,
            CostRecord.timestamp == now,
            CostRecord.service == "AmazonEC2",
        )
    )
    assert record is not None
    assert record.cost_status == "FINAL"
    assert record.is_preliminary is False

    async def record_stream():
        yield {
            "provider": "aws",
            "service": "AmazonEC2",
            "region": "us-east-1",
            "usage_type": "BoxUsage",
            "currency": "USD",
            "timestamp": now,
            "cost_usd": Decimal("75.00"),
            "source_adapter": "cur_adapter",
        }

    run_id = uuid4()
    await service.save_records_stream(
        record_stream(),
        tenant_id=str(tenant.id),
        account_id=str(account.id),
        reconciliation_run_id=run_id,
        is_preliminary=True,
    )

    updated = await db.scalar(
        select(CostRecord).where(
            CostRecord.account_id == account.id,
            CostRecord.timestamp == now,
            CostRecord.service == "AmazonEC2",
        )
    )
    assert updated is not None
    assert updated.cost_usd == Decimal("75.00")
    assert updated.cost_status == "FINAL"
    assert updated.is_preliminary is False

    logs = (
        (
            await db.execute(
                select(CostAuditLog).where(
                    CostAuditLog.cost_record_id == updated.id,
                    CostAuditLog.cost_recorded_at == updated.recorded_at,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert float(logs[0].old_cost) == 50.0
    assert float(logs[0].new_cost) == 75.0
    assert logs[0].ingestion_batch_id == run_id
