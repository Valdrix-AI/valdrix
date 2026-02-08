import pytest
import uuid
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from app.models.aws_connection import AWSConnection
from app.models.tenant import Tenant
from app.models.background_job import JobType, JobStatus
from app.models.cloud import CostRecord as CostRecordModel
from app.modules.governance.domain.jobs.processor import JobProcessor, enqueue_job

@pytest.mark.asyncio
async def test_end_to_end_cost_ingestion_pipeline(db):
    # Set RLS context for the session
    tenant_id = uuid.uuid4()
    from app.shared.db.session import set_session_tenant_id
    await set_session_tenant_id(db, tenant_id)
    
    # 1. Setup Initial Data
    tenant = Tenant(id=tenant_id, name="Enterprise Corp", plan="enterprise")
    
    db.add(tenant)
    await db.flush()
    await db.refresh(tenant)
    print(f"DEBUG: Created Tenant ID: {tenant.id}")
    
    # Set context
    await set_session_tenant_id(db, tenant.id)

    connection = AWSConnection(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/Valdrix",
        external_id="ext-123",
        region="us-east-1",
        cur_bucket_name="test-cur-bucket",
        cur_status="active"
    )
    db.add(connection)
    await db.flush()

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
    
    async def mock_stream(*args, **kwargs):
        for r in mock_summary.records:
            yield {
                "timestamp": r.date,
                "service": r.service,
                "region": r.region,
                "cost_usd": float(r.amount),
                "currency": "USD",
                "amount_raw": float(r.amount),
                "usage_type": r.usage_type
            }
            
    mock_adapter.stream_cost_and_usage = mock_stream

    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
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
        await set_session_tenant_id(db, tenant.id)
        
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
    await enqueue_job(
            db=db,
            job_type=JobType.COST_INGESTION,
            tenant_id=tenant.id
    )
    
    with patch("app.shared.adapters.factory.AdapterFactory.get_adapter", return_value=mock_adapter):
        await processor.process_pending_jobs(limit=1)
        
        result = await db.execute(
            select(CostRecordModel).where(CostRecordModel.account_id == connection.id)
        )
        records = result.scalars().all()
        assert len(records) == 2
