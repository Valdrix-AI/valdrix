from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.reporting.domain.reconciliation import CostReconciliationService


def test_reconciliation_helper_paths() -> None:
    assert CostReconciliationService._normalize_source("cur_parquet") == "cur"
    assert CostReconciliationService._normalize_source("cost_explorer_api") == "explorer"
    assert CostReconciliationService._normalize_source("  ") == "unknown"
    assert CostReconciliationService._normalize_cloud_plus_source("saas_feed", "saas") == "feed"
    assert CostReconciliationService._normalize_cloud_plus_source("saas_stripe_api", "saas") == "native"
    assert CostReconciliationService._normalize_cloud_plus_source("license_feed", "license") == "feed"
    assert CostReconciliationService._compute_confidence(10, 5, 1000) == 0.7
    assert CostReconciliationService._compute_confidence(0, 0, 0) == 0.0
    assert CostReconciliationService._to_float(None) == 0.0
    assert CostReconciliationService._to_int(None) == 0


def test_reconciliation_csv_renderers_and_hash() -> None:
    entries = [
        {
            "usage_date": "2026-01-01",
            "recorded_at": "2026-01-02T00:00:00+00:00",
            "service": "Compute",
            "region": "us-east-1",
            "old_cost": 10.0,
            "new_cost": 12.0,
            "delta_usd": 2.0,
            "reason": "RE-INGESTION",
            "cost_record_id": "id-1",
            "ingestion_batch_id": "batch-1",
        }
    ]
    close_csv = CostReconciliationService._render_close_package_csv(
        tenant_id="t-1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        close_status="ready",
        lifecycle_summary={"total_records": 1},
        reconciliation_summary={"status": "healthy", "discrepancies": []},
        restatement_entries=entries,
    )
    rest_csv = CostReconciliationService._render_restatements_csv(entries)
    assert "close_status" in close_csv
    assert "restatements" in close_csv
    assert "usage_date,recorded_at,service" in rest_csv
    assert (
        CostReconciliationService._stable_hash({"a": 1})
        == CostReconciliationService._stable_hash({"a": 1})
    )


@pytest.mark.asyncio
async def test_get_restatement_history_with_csv_export() -> None:
    db = MagicMock()
    row = SimpleNamespace(
        audit_recorded_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        cost_record_id=uuid4(),
        old_cost=Decimal("10"),
        new_cost=Decimal("13"),
        reason="RECON",
        ingestion_batch_id="batch-1",
        service="S3",
        region="us-east-1",
        usage_date=date(2026, 1, 1),
    )
    result = MagicMock()
    result.all.return_value = [row]
    db.execute = AsyncMock(return_value=result)
    service = CostReconciliationService(db)

    payload = await service.get_restatement_history(
        tenant_id=uuid4(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        export_csv=True,
    )
    assert payload["restatement_count"] == 1
    assert payload["net_delta_usd"] == 3.0
    assert "csv" in payload


@pytest.mark.asyncio
async def test_generate_close_package_ready_and_blocked_paths() -> None:
    db = MagicMock()
    lifecycle_row = SimpleNamespace(
        total_records=10,
        preliminary_records=0,
        final_records=10,
        total_cost_usd=Decimal("100"),
        preliminary_cost_usd=Decimal("0"),
        final_cost_usd=Decimal("100"),
    )
    lifecycle_result = MagicMock()
    lifecycle_result.one.return_value = lifecycle_row
    db.execute = AsyncMock(return_value=lifecycle_result)
    service = CostReconciliationService(db)

    with patch.object(service, "compare_explorer_vs_cur", new=AsyncMock(return_value={"status": "healthy"})), patch.object(
        service,
        "get_restatement_history",
        new=AsyncMock(return_value={"restatement_count": 0, "net_delta_usd": 0.0, "absolute_delta_usd": 0.0, "entries": []}),
    ):
        package = await service.generate_close_package(
            tenant_id=uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            enforce_finalized=True,
        )
    assert package["close_status"] == "ready"
    assert "integrity_hash" in package
    assert "csv" in package

    blocked_row = SimpleNamespace(
        total_records=5,
        preliminary_records=2,
        final_records=3,
        total_cost_usd=Decimal("50"),
        preliminary_cost_usd=Decimal("10"),
        final_cost_usd=Decimal("40"),
    )
    blocked_result = MagicMock()
    blocked_result.one.return_value = blocked_row
    db.execute = AsyncMock(return_value=blocked_result)
    with pytest.raises(ValueError, match="preliminary records exist"):
        await service.generate_close_package(
            tenant_id=uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            enforce_finalized=True,
        )


@pytest.mark.asyncio
async def test_compare_explorer_vs_cur_alert_failure_path() -> None:
    db = MagicMock()
    rows = [
        SimpleNamespace(service="Compute", source_adapter="cur_parquet", total_cost=100.0, record_count=5),
        SimpleNamespace(service="Compute", source_adapter="cost_explorer_api", total_cost=110.0, record_count=5),
        SimpleNamespace(service="Storage", source_adapter="cur_parquet", total_cost=50.0, record_count=2),
        SimpleNamespace(service="Storage", source_adapter="cost_explorer_api", total_cost=49.0, record_count=2),
    ]
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    service = CostReconciliationService(db)

    with patch(
        "app.shared.core.notifications.NotificationDispatcher.send_alert",
        new=AsyncMock(side_effect=RuntimeError("alert failed")),
    ):
        summary = await service.compare_explorer_vs_cur(
            tenant_id=uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            alert_threshold_pct=1.0,
        )
    assert summary["status"] == "warning"
    assert summary["alert_triggered"] is False
    assert summary["alert_error"] == "alert failed"
    assert summary["source_totals"]["cur"] == 150.0
    assert summary["source_totals"]["explorer"] == 159.0


@pytest.mark.asyncio
async def test_compare_cloud_plus_native_vs_feed() -> None:
    db = MagicMock()
    rows = [
        SimpleNamespace(service="Salesforce Contract", source_adapter="saas_feed", total_cost=100.0, record_count=5),
        SimpleNamespace(service="Salesforce Contract", source_adapter="saas_salesforce_api", total_cost=96.0, record_count=5),
    ]
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    service = CostReconciliationService(db)

    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        provider="saas",
        alert_threshold_pct=1.0,
    )
    assert summary["comparison_basis"] == "native_vs_feed"
    assert summary["source_totals"]["native"] == 96.0
    assert summary["source_totals"]["feed"] == 100.0
    assert summary["status"] == "warning"
    assert summary["impacted_services"][0]["native_cost"] == 96.0
    assert summary["impacted_services"][0]["feed_cost"] == 100.0
