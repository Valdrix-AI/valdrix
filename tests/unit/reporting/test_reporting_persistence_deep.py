import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, date, timezone
from uuid import uuid4
from decimal import Decimal
from app.modules.reporting.domain.persistence import CostPersistenceService
from app.schemas.costs import CloudUsageSummary, CostRecord as CostRecordSchema

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # add and add_all are sync methods in AsyncSession
    db.add = MagicMock()
    db.add_all = MagicMock()
    # Mocking db.bind.url for the _bulk_upsert logic
    db.bind = MagicMock()
    db.bind.url = "postgresql://user:pass@localhost/db"
    return db

@pytest.fixture
def persistence_service(mock_db):
    return CostPersistenceService(mock_db)

@pytest.fixture
def sample_summary():
    tenant_id = str(uuid4())
    now = datetime.now(timezone.utc)
    return CloudUsageSummary(
        tenant_id=tenant_id,
        provider="aws",
        start_date=now.date(),
        end_date=now.date(),
        total_cost=Decimal("10.00"),
        records=[
            CostRecordSchema(
                date=now,
                amount=Decimal("10.00"),
                service="AmazonEC2",
                region="us-east-1",
                usage_type="BoxUsage"
            )
        ]
    )

@pytest.mark.asyncio
async def test_save_summary_postgresql_path(persistence_service, mock_db, sample_summary):
    # Test the PostgreSQL bulk upsert path
    account_id = str(uuid4())
    
    await persistence_service.save_summary(sample_summary, account_id)
    
    assert mock_db.execute.called
    assert mock_db.flush.called
    # Check that we log success
    # No direct assertion on logger here unless we wrap it, but we can check if execute was called with correct stmt

@pytest.mark.asyncio
async def test_save_summary_sqlite_path(persistence_service, mock_db, sample_summary):
    # Force SQLite path
    mock_db.bind.url = "sqlite+aiosqlite:///:memory:"
    account_id = str(uuid4())
    
    # Mock result for existing check
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None # Not existing
    mock_db.execute.return_value = mock_result
    
    await persistence_service.save_summary(sample_summary, account_id)
    
    assert mock_db.add.called
    assert mock_db.flush.called

@pytest.mark.asyncio
async def test_save_summary_sqlite_idempotency(persistence_service, mock_db, sample_summary):
    mock_db.bind.url = "sqlite+aiosqlite:///:memory:"
    account_id = str(uuid4())
    
    # Mock existing record
    existing_record = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_record
    mock_db.execute.return_value = mock_result
    
    await persistence_service.save_summary(sample_summary, account_id)
    
    assert existing_record.cost_usd == Decimal("10.00")
    assert not mock_db.add.called
    assert mock_db.flush.called

@pytest.mark.asyncio
async def test_save_records_stream(persistence_service, mock_db):
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    
    async def record_stream():
        for i in range(3):
            yield {
                "service": "S3",
                "region": "us-east-1",
                "cost_usd": Decimal("1.00"),
                "timestamp": datetime.now(timezone.utc),
                "usage_type": "DataTransfer"
            }
            
    result = await persistence_service.save_records_stream(record_stream(), tenant_id, account_id)
    assert result["records_saved"] == 3
    assert mock_db.execute.called

@pytest.mark.asyncio
async def test_check_for_significant_adjustments_no_change(persistence_service, mock_db):
    # Test _check_for_significant_adjustments where costs are same
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    new_records = [{
        "timestamp": now,
        "service": "EC2",
        "region": "us-east-1",
        "cost_usd": 10.0
    }]
    
    # Mock existing record with same cost
    mock_res = MagicMock()
    mock_res.all.return_value = [
        MagicMock(timestamp=now, service="EC2", region="us-east-1", cost_usd=Decimal("10.00"), id=uuid4())
    ]
    mock_db.execute.return_value = mock_res
    
    await persistence_service._check_for_significant_adjustments(tenant_id, account_id, new_records)
    assert not mock_db.add_all.called

@pytest.mark.asyncio
async def test_check_for_significant_adjustments_with_audit_log(persistence_service, mock_db):
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    new_records = [{
        "timestamp": now,
        "service": "EC2",
        "region": "us-east-1",
        "cost_usd": 11.0 # Significant change (>2% of 10.0)
    }]
    
    # Mock existing record with different cost
    rec_id = uuid4()
    mock_res = MagicMock()
    mock_res.all.return_value = [
        MagicMock(timestamp=now, service="EC2", region="us-east-1", cost_usd=Decimal("10.00"), id=rec_id)
    ]
    mock_db.execute.return_value = mock_res
    
    await persistence_service._check_for_significant_adjustments(tenant_id, account_id, new_records)
    assert mock_db.add_all.called
    # Verify audit log was added
    audit_logs = mock_db.add_all.call_args[0][0]
    assert len(audit_logs) == 1
    assert audit_logs[0].old_cost == Decimal("10.00")
    assert audit_logs[0].new_cost == Decimal("11.0")

@pytest.mark.asyncio
async def test_save_summary_non_preliminary(persistence_service, mock_db, sample_summary):
    # Test path where is_preliminary=False, triggering adjustment check
    account_id = str(uuid4())
    
    # Mock adjustment check
    with patch.object(persistence_service, '_check_for_significant_adjustments', AsyncMock()) as mock_check:
        await persistence_service.save_summary(sample_summary, account_id, is_preliminary=False)
        assert mock_check.called

@pytest.mark.asyncio
async def test_check_for_significant_adjustments_no_existing(persistence_service, mock_db):
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    new_records = [{
        "timestamp": now,
        "service": "EC2",
        "region": "us-east-1",
        "cost_usd": 10.0
    }]
    
    # Mock no existing records
    mock_res = MagicMock()
    mock_res.all.return_value = []
    mock_db.execute.return_value = mock_res
    
    await persistence_service._check_for_significant_adjustments(tenant_id, account_id, new_records)
    assert not mock_db.add_all.called

@pytest.mark.asyncio
async def test_check_for_significant_adjustments_significant(persistence_service, mock_db):
    tenant_id = str(uuid4())
    account_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    new_records = [{
        "timestamp": now,
        "service": "EC2",
        "region": "us-east-1",
        "cost_usd": 15.0 # Significant adjustment from 10.0
    }]
    
    rec_id = uuid4()
    mock_res = MagicMock()
    mock_res.all.return_value = [
        MagicMock(timestamp=now, service="EC2", region="us-east-1", cost_usd=Decimal("10.00"), id=rec_id)
    ]
    mock_db.execute.return_value = mock_res
    
    await persistence_service._check_for_significant_adjustments(tenant_id, account_id, new_records)
    assert mock_db.add_all.called

@pytest.mark.asyncio
async def test_clear_range_basic(persistence_service, mock_db):
    await persistence_service.clear_range("acc-123", date(2026,1,1), date(2026,1,31))
    assert mock_db.execute.called

@pytest.mark.asyncio
async def test_cleanup_loops(persistence_service, mock_db):
    # Test the loop in cleanup_old_records
    mock_res_ids = MagicMock()
    mock_res_ids.scalars.return_value.all.side_effect = [[uuid4()], []]
    
    mock_db.execute.return_value = mock_res_ids
    
    await persistence_service.cleanup_old_records(days_retention=30)
    assert mock_db.flush.called

@pytest.mark.asyncio
async def test_finalize_batch_success(persistence_service, mock_db):
    mock_res = MagicMock()
    mock_res.rowcount = 10
    mock_db.execute.return_value = mock_res
    
    result = await persistence_service.finalize_batch(days_ago=2)
    assert result["records_finalized"] == 10
    assert mock_db.flush.called
