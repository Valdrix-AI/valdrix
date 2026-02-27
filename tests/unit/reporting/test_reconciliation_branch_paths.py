from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.models.invoice import ProviderInvoice
from app.models.pricing import ExchangeRate
from app.models.tenant import Tenant
from app.modules.reporting.domain.reconciliation import CostReconciliationService


def test_reconciliation_helper_paths() -> None:
    assert CostReconciliationService._normalize_source("cur_parquet") == "cur"
    assert (
        CostReconciliationService._normalize_source("cost_explorer_api") == "explorer"
    )
    assert CostReconciliationService._normalize_source("  ") == "unknown"
    assert (
        CostReconciliationService._normalize_cloud_plus_source("saas_feed", "saas")
        == "feed"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "saas_stripe_api", "saas"
        )
        == "native"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "license_feed", "license"
        )
        == "feed"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "platform_feed", "platform"
        )
        == "feed"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "hybrid_openstack", "hybrid"
        )
        == "native"
    )
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
        invoice_reconciliation=None,
        restatement_entries=entries,
    )
    rest_csv = CostReconciliationService._render_restatements_csv(entries)
    assert "close_status" in close_csv
    assert "restatements" in close_csv
    assert "usage_date,recorded_at,service" in rest_csv
    assert CostReconciliationService._stable_hash(
        {"a": 1}
    ) == CostReconciliationService._stable_hash({"a": 1})


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

    with (
        patch.object(
            service,
            "compare_explorer_vs_cur",
            new=AsyncMock(return_value={"status": "healthy"}),
        ),
        patch.object(
            service,
            "get_restatement_history",
            new=AsyncMock(
                return_value={
                    "restatement_count": 0,
                    "net_delta_usd": 0.0,
                    "absolute_delta_usd": 0.0,
                    "entries": [],
                }
            ),
        ),
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
        SimpleNamespace(
            service="Compute",
            source_adapter="cur_parquet",
            total_cost=100.0,
            record_count=5,
        ),
        SimpleNamespace(
            service="Compute",
            source_adapter="cost_explorer_api",
            total_cost=110.0,
            record_count=5,
        ),
        SimpleNamespace(
            service="Storage",
            source_adapter="cur_parquet",
            total_cost=50.0,
            record_count=2,
        ),
        SimpleNamespace(
            service="Storage",
            source_adapter="cost_explorer_api",
            total_cost=49.0,
            record_count=2,
        ),
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
@pytest.mark.parametrize(
    ("provider", "feed_source", "native_source"),
    [
        ("saas", "saas_feed", "saas_salesforce_api"),
        ("license", "license_feed", "license_microsoft_graph"),
        ("platform", "platform_feed", "platform_datadog_api"),
        ("hybrid", "hybrid_feed", "hybrid_openstack_api"),
    ],
)
async def test_compare_cloud_plus_native_vs_feed(
    provider: str, feed_source: str, native_source: str
) -> None:
    db = MagicMock()
    rows = [
        SimpleNamespace(
            service="Salesforce Contract",
            source_adapter=feed_source,
            total_cost=100.0,
            record_count=5,
        ),
        SimpleNamespace(
            service="Salesforce Contract",
            source_adapter=native_source,
            total_cost=96.0,
            record_count=5,
        ),
    ]
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    service = CostReconciliationService(db)

    summary = await service.compare_explorer_vs_cur(
        tenant_id=uuid4(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        provider=provider,
        alert_threshold_pct=1.0,
    )
    assert summary["comparison_basis"] == "native_vs_feed"
    assert summary["source_totals"]["native"] == 96.0
    assert summary["source_totals"]["feed"] == 100.0
    assert summary["status"] == "warning"
    assert summary["impacted_services"][0]["native_cost"] == 96.0
    assert summary["impacted_services"][0]["feed_cost"] == 100.0


def test_reconciliation_normalizers_cover_error_and_unknown_paths() -> None:
    assert CostReconciliationService._normalize_provider("  ") is None
    with pytest.raises(ValueError, match="Unsupported provider"):
        CostReconciliationService._normalize_provider("digitalocean")

    assert (
        CostReconciliationService._normalize_cloud_plus_source("native", "saas")
        == "native"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "not-mapped-source", "saas"
        )
        == "unknown"
    )
    assert (
        CostReconciliationService._normalize_cloud_plus_source(
            "explorer", "aws"
        )
        == "unknown"
    )


def test_render_restatement_runs_csv_path() -> None:
    runs = [
        {
            "ingestion_batch_id": "batch-1",
            "entry_count": 2,
            "net_delta_usd": 3.0,
            "absolute_delta_usd": 3.0,
            "first_recorded_at": "2026-01-01T00:00:00+00:00",
            "last_recorded_at": "2026-01-02T00:00:00+00:00",
            "integrity_hash": "hash-a",
        }
    ]
    csv_payload = CostReconciliationService._render_restatement_runs_csv(runs)
    assert "ingestion_batch_id,entry_count,net_delta_usd" in csv_payload
    assert "batch-1" in csv_payload
    assert "hash-a" in csv_payload


@pytest.mark.asyncio
async def test_get_restatement_runs_with_csv_export_and_provider_filter() -> None:
    db = MagicMock()
    rows = [
        SimpleNamespace(
            ingestion_batch_id="batch-2",
            entry_count=2,
            net_delta_usd=Decimal("1.5"),
            absolute_delta_usd=Decimal("2.5"),
            first_recorded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            last_recorded_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            ingestion_batch_id=None,
            entry_count=1,
            net_delta_usd=Decimal("-0.5"),
            absolute_delta_usd=Decimal("0.5"),
            first_recorded_at=None,
            last_recorded_at=None,
        ),
    ]
    db.execute = AsyncMock(return_value=SimpleNamespace(all=lambda: rows))
    service = CostReconciliationService(db)

    payload = await service.get_restatement_runs(
        tenant_id=uuid4(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        export_csv=True,
        provider="aws",
    )
    assert payload["provider"] == "aws"
    assert payload["run_count"] == 2
    assert payload["runs"][0]["ingestion_batch_id"] == "batch-2"
    assert payload["runs"][1]["ingestion_batch_id"] is None
    assert "csv" in payload
    assert "integrity_hash" in payload["runs"][0]


@pytest.mark.asyncio
async def test_generate_close_package_with_invoice_summary_and_restatement_truncation() -> None:
    db = MagicMock()
    lifecycle_row = SimpleNamespace(
        total_records=20,
        preliminary_records=0,
        final_records=20,
        total_cost_usd=Decimal("200"),
        preliminary_cost_usd=Decimal("0"),
        final_cost_usd=Decimal("200"),
    )
    db.execute = AsyncMock(return_value=SimpleNamespace(one=lambda: lifecycle_row))
    service = CostReconciliationService(db)

    with (
        patch.object(
            service,
            "compare_explorer_vs_cur",
            new=AsyncMock(return_value={"status": "healthy"}),
        ),
        patch.object(
            service,
            "get_invoice_reconciliation_summary",
            new=AsyncMock(return_value={"status": "match", "provider": "aws"}),
        ),
        patch.object(
            service,
            "get_restatement_history",
            new=AsyncMock(
                return_value={
                    "restatement_count": 2,
                    "net_delta_usd": 1.0,
                    "absolute_delta_usd": 1.0,
                    "entries": [
                        {
                            "usage_date": "2026-01-01",
                            "recorded_at": "2026-01-02T00:00:00+00:00",
                            "service": "S3",
                            "region": "us-east-1",
                            "old_cost": 10.0,
                            "new_cost": 11.0,
                            "delta_usd": 1.0,
                            "reason": "RECON",
                            "cost_record_id": "cost-1",
                            "ingestion_batch_id": "b1",
                        },
                        {
                            "usage_date": "2026-01-01",
                            "recorded_at": "2026-01-02T00:00:00+00:00",
                            "service": "EC2",
                            "region": "us-east-1",
                            "old_cost": 20.0,
                            "new_cost": 20.0,
                            "delta_usd": 0.0,
                            "reason": "RECON",
                            "cost_record_id": "cost-2",
                            "ingestion_batch_id": "b2",
                        },
                    ],
                }
            ),
        ),
    ):
        package = await service.generate_close_package(
            tenant_id=uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            max_restatement_entries=1,
        )

    assert package["provider"] == "aws"
    assert package["invoice_reconciliation"]["status"] == "match"
    assert package["restatements"]["truncated"] is True
    assert package["restatements"]["included_count"] == 1


@pytest.mark.asyncio
async def test_invoice_crud_and_status_update_paths(db) -> None:
    tenant = Tenant(
        id=uuid4(),
        name="reconciliation-invoice-tenant",
        plan="pro",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()

    service = CostReconciliationService(db)

    with pytest.raises(ValueError, match="start_date must be <= end_date"):
        await service.upsert_invoice(
            tenant.id,
            provider="aws",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 31),
            currency="USD",
            total_amount=Decimal("10"),
        )

    invoice = await service.upsert_invoice(
        tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        currency="USD",
        total_amount=Decimal("100.00"),
        invoice_number="INV-1",
        status="Issued",
        notes="initial",
    )
    assert invoice.status == "issued"

    invoice_updated = await service.upsert_invoice(
        tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        currency="USD",
        total_amount=Decimal("125.00"),
        notes="revised",
    )
    assert invoice_updated.id == invoice.id
    assert Decimal(str(invoice_updated.total_amount)) == Decimal("125.00")

    listed = await service.list_invoices(
        tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    assert len(listed) == 1

    loaded = await service.get_invoice(tenant.id, invoice.id)
    assert loaded is not None

    status_updated = await service.update_invoice_status(
        tenant.id,
        invoice.id,
        status="PAID",
        notes="settled",
    )
    assert status_updated is not None
    assert status_updated.status == "paid"
    assert status_updated.notes == "settled"

    missing_status_update = await service.update_invoice_status(
        tenant.id,
        uuid4(),
        status="PAID",
    )
    assert missing_status_update is None

    assert await service.delete_invoice(tenant.id, invoice.id) is True
    assert await service.delete_invoice(tenant.id, invoice.id) is False
    assert await service.get_invoice(tenant.id, invoice.id) is None


@pytest.mark.asyncio
async def test_invoice_exchange_rate_and_reconciliation_summary_paths(db) -> None:
    tenant = Tenant(
        id=uuid4(),
        name="reconciliation-exchange-tenant",
        plan="pro",
        is_deleted=False,
    )
    db.add(tenant)
    await db.commit()

    service = CostReconciliationService(db)
    assert await service._invoice_total_to_usd(Decimal("15"), "USD") == Decimal("15")

    db.add(
        ExchangeRate(
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("0.5000"),
            provider="seed",
        )
    )
    await db.commit()
    assert await service._invoice_total_to_usd(Decimal("100"), "EUR") == Decimal("2E+2")

    db.add(
        ExchangeRate(
            from_currency="USD",
            to_currency="CAD",
            rate=Decimal("-1"),
            provider="seed",
        )
    )
    await db.commit()
    with pytest.raises(ValueError, match="Invalid exchange rate for USD->CAD"):
        await service._invoice_total_to_usd(Decimal("100"), "CAD")

    db.add(
        ExchangeRate(
            from_currency="JPY",
            to_currency="USD",
            rate=Decimal("0.0100"),
            provider="seed",
        )
    )
    await db.commit()
    assert await service._invoice_total_to_usd(Decimal("100"), "JPY") == Decimal("1")

    db.add(
        ExchangeRate(
            from_currency="CHF",
            to_currency="USD",
            rate=Decimal("-1"),
            provider="seed",
        )
    )
    await db.commit()
    with pytest.raises(ValueError, match="Invalid exchange rate for CHF->USD"):
        await service._invoice_total_to_usd(Decimal("100"), "CHF")

    with pytest.raises(ValueError, match="Missing exchange rate for invoice currency GBP"):
        await service._invoice_total_to_usd(Decimal("100"), "GBP")

    missing_invoice_summary = await service.get_invoice_reconciliation_summary(
        tenant_id=tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        ledger_final_cost_usd=100.0,
        threshold_percent=1.0,
    )
    assert missing_invoice_summary["status"] == "missing_invoice"

    await service.upsert_invoice(
        tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        currency="USD",
        total_amount=Decimal("100.00"),
        invoice_number="INV-100",
        status="posted",
    )
    summary_match = await service.get_invoice_reconciliation_summary(
        tenant_id=tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        ledger_final_cost_usd=100.5,
        threshold_percent=1.0,
    )
    assert summary_match["status"] == "match"
    assert "integrity_hash" in summary_match

    summary_mismatch = await service.get_invoice_reconciliation_summary(
        tenant_id=tenant.id,
        provider="aws",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        ledger_final_cost_usd=150.0,
        threshold_percent=1.0,
    )
    assert summary_mismatch["status"] == "mismatch"

    await db.execute(delete(ProviderInvoice))
    await db.execute(delete(ExchangeRate))
    await db.commit()
