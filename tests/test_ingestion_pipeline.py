import pytest
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import sqlalchemy as sa
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.models.tenant import Tenant
from app.models.background_job import BackgroundJob, JobType, JobStatus
from app.models.cloud import CostRecord as CostRecordModel
from app.services.jobs.processor import JobProcessor, enqueue_job

@pytest.mark.asyncio
async def test_end_to_end_cost_ingestion_pipeline(db):
    print("DEBUG: STARTING TEST CLEAN")
    sys.stdout.flush()
    
    # Disable RLS and Cleanup for test
    await db.execute(sa.text("ALTER TABLE background_jobs DISABLE ROW LEVEL SECURITY"))
    await db.execute(sa.text("ALTER TABLE cost_records DISABLE ROW LEVEL SECURITY"))
    await db.execute(sa.text("ALTER TABLE cloud_accounts DISABLE ROW LEVEL SECURITY"))
    await db.execute(sa.text("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY"))
    await db.execute(sa.text("ALTER TABLE users DISABLE ROW LEVEL SECURITY"))
    
    await db.execute(sa.text("DELETE FROM background_jobs"))
    await db.execute(sa.text("DELETE FROM cost_records"))
    await db.execute(sa.text("DELETE FROM aws_connections"))
    await db.execute(sa.text("DELETE FROM users"))
    await db.execute(sa.text("DELETE FROM tenants"))
    await db.commit()
    
    # 1. Setup Tenant and Connection
    tenant = Tenant(name="Enterprise Corp", plan="enterprise")
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    print(f"DEBUG: Created Tenant ID: {tenant.id}")
    
    # Set context
    await db.execute(sa.text(f"SET app.current_tenant_id = '{tenant.id}'"))

    connection = AWSConnection(
        tenant_id=tenant.id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/Valdrix",
        external_id="ext-123",
        region="us-east-1",
        cur_bucket_name="test-cur-bucket",
        cur_status="active"
    )
    db.add(connection)
    await db.commit()

    # 2. Mock the AWSCURAdapter to return sample data instead of calling S3
    from app.schemas.costs import CloudUsageSummary, CostRecord as CostRecordSchema
    
    sample_now = datetime.now(timezone.utc)
    mock_summary = CloudUsageSummary(
        tenant_id=str(tenant.id),
        provider="aws",
        start_date=sample_now.date(),
        end_date=sample_now.date(),
        total_cost=Decimal("150.00"),
        records=[
            CostRecordSchema(
                date=sample_now,
                amount=Decimal("100.00"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage"
            ),
            CostRecordSchema(
                date=sample_now,
                amount=Decimal("50.00"),
                service="AmazonS3",
                region="us-east-1",
                usage_type="PutRequests"
            )
        ]
    )

    # Patch the Factory to return our mock summary
    mock_adapter = AsyncMock()
    mock_adapter.get_costs.return_value = mock_summary

    with patch("app.services.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
        # 3. Enqueue the job
        job = await enqueue_job(
            db=db,
            job_type=JobType.COST_INGESTION,
            tenant_id=tenant.id
        )
        await db.refresh(job)
        print(f"DEBUG: Enqueued Job ID: {job.id}, Tenant ID: {job.tenant_id}")
        sys.stdout.flush()
            
        assert job.status == JobStatus.PENDING.value
            
        # 4. Process the job
        processor = JobProcessor(db)
        # Force the processor to see the job by bypassing RLS if needed, but here we set context
        await db.execute(sa.text(f"SET app.current_tenant_id = '{tenant.id}'"))
        
        results = await processor.process_pending_jobs(limit=1)
        print(f"DEBUG: Process results: {results}")
        sys.stdout.flush()
        
        # 5. Verify Database State
        await db.refresh(job)
        print(f"DEBUG: Job Final Status: {job.status}, Error: {job.error_message}")
        
        assert job.status == JobStatus.COMPLETED.value
        
        # Check Cost Records
        result = await db.execute(
            select(CostRecordModel).where(CostRecordModel.account_id == connection.id)
        )
        records = result.scalars().all()
        assert len(records) == 2
        
        ec2_record = next(r for r in records if r.service == "AmazonEC2")
        assert ec2_record.cost_usd == Decimal("100.00")

    # 6. Verify Idempotency 
    job2 = await enqueue_job(
            db=db,
            job_type=JobType.COST_INGESTION,
            tenant_id=tenant.id
    )
    
    with patch("app.services.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
        await processor.process_pending_jobs(limit=1)
        
        result = await db.execute(
            select(CostRecordModel).where(CostRecordModel.account_id == connection.id)
        )
        records = result.scalars().all()
        assert len(records) == 2
