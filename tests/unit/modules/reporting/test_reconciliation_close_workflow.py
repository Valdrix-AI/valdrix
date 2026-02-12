from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.domain.reconciliation import CostReconciliationService


def _result_with_one(row: object) -> MagicMock:
    result = MagicMock()
    result.one.return_value = row
    return result


def _result_with_all(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_generate_close_package_blocks_when_preliminary_records_exist() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    lifecycle_row = SimpleNamespace(
        total_records=12,
        preliminary_records=3,
        final_records=9,
        total_cost_usd=Decimal("120.00"),
        preliminary_cost_usd=Decimal("20.00"),
        final_cost_usd=Decimal("100.00"),
    )
    db.execute = AsyncMock(return_value=_result_with_one(lifecycle_row))

    service = CostReconciliationService(db)
    with patch.object(service, "compare_explorer_vs_cur", AsyncMock()) as mock_compare:
        with pytest.raises(ValueError, match="preliminary records exist"):
            await service.generate_close_package(
                tenant_id=tenant_id,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                enforce_finalized=True,
            )
    mock_compare.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_close_package_is_stable_and_includes_restatements() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    lifecycle_row = SimpleNamespace(
        total_records=10,
        preliminary_records=0,
        final_records=10,
        total_cost_usd=Decimal("200.00"),
        preliminary_cost_usd=Decimal("0.00"),
        final_cost_usd=Decimal("200.00"),
    )
    restatement_rows = [
        SimpleNamespace(
            usage_date=date(2026, 1, 4),
            audit_recorded_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
            service="Zendesk",
            region="global",
            old_cost=Decimal("50.00"),
            new_cost=Decimal("55.00"),
            reason="RE-INGESTION",
            cost_record_id=uuid4(),
            ingestion_batch_id=uuid4(),
        ),
        SimpleNamespace(
            usage_date=date(2026, 1, 2),
            audit_recorded_at=datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc),
            service="Salesforce",
            region="global",
            old_cost=Decimal("100.00"),
            new_cost=Decimal("98.00"),
            reason="CREDIT",
            cost_record_id=uuid4(),
            ingestion_batch_id=uuid4(),
        ),
    ]
    db.execute = AsyncMock(
        side_effect=[
            _result_with_one(lifecycle_row),
            _result_with_all(restatement_rows),
            _result_with_one(lifecycle_row),
            _result_with_all(restatement_rows),
        ]
    )

    reconciliation_summary = {
        "status": "healthy",
        "total_records": 10,
        "total_cost": 200.0,
        "discrepancy_percentage": 0.0,
        "impacted_services": [],
        "discrepancies": [],
    }

    service = CostReconciliationService(db)
    with patch.object(
        service,
        "compare_explorer_vs_cur",
        AsyncMock(return_value=reconciliation_summary),
    ):
        first = await service.generate_close_package(
            tenant_id=tenant_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        second = await service.generate_close_package(
            tenant_id=tenant_id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

    assert first["close_status"] == "ready"
    assert first["restatements"]["count"] == 2
    assert first["integrity_hash"] == second["integrity_hash"]
    assert first["csv"] == second["csv"]
    assert "section,key,value" in first["csv"]
    assert "Salesforce" in first["csv"]


@pytest.mark.asyncio
async def test_get_restatement_history_supports_csv_export() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    rows = [
        SimpleNamespace(
            usage_date=date(2026, 1, 8),
            audit_recorded_at=datetime(2026, 2, 2, 12, 0, tzinfo=timezone.utc),
            service="Atlassian",
            region="global",
            old_cost=Decimal("40.00"),
            new_cost=Decimal("42.00"),
            reason="RE-INGESTION",
            cost_record_id=uuid4(),
            ingestion_batch_id=uuid4(),
        )
    ]
    db.execute = AsyncMock(return_value=_result_with_all(rows))

    service = CostReconciliationService(db)
    payload = await service.get_restatement_history(
        tenant_id=tenant_id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        export_csv=True,
    )

    assert payload["restatement_count"] == 1
    assert payload["net_delta_usd"] == 2.0
    assert payload["entries"][0]["service"] == "Atlassian"
    assert payload["csv"].startswith("usage_date,recorded_at,service,region,old_cost")
