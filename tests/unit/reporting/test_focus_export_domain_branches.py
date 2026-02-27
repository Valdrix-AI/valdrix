from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.modules.reporting.domain import focus_export as focus_export_module
from app.modules.reporting.domain.focus_export import (
    FocusAccountContext,
    FocusV13ExportService,
)


class _RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows

    def __iter__(self):
        return iter(self._rows)


def _service_with_mock_db() -> FocusV13ExportService:
    db = SimpleNamespace()
    db.stream = AsyncMock()
    db.execute = AsyncMock()
    return FocusV13ExportService(db=db)


def test_focus_export_helper_branches() -> None:
    assert focus_export_module._next_month_start(date(2026, 12, 31)) == datetime(
        2027, 1, 1, tzinfo=timezone.utc
    )
    assert focus_export_module._humanize_vendor("  microsoft_365  ") == "Microsoft 365"
    assert focus_export_module._humanize_vendor("new-relic") == "New Relic"
    assert focus_export_module._humanize_vendor(None) is None

    assert (
        focus_export_module._service_provider_display("saas", "salesforce")
        == "Salesforce"
    )
    assert (
        focus_export_module._focus_charge_category("invoice tax", "x")
        == "Tax"
    )
    assert (
        focus_export_module._focus_charge_category("refund", "credit")
        == "Credit"
    )
    assert (
        focus_export_module._focus_charge_category("marketplace fee", None)
        == "Adjustment"
    )
    assert focus_export_module._focus_charge_frequency("Adjustment") == "One-Time"
    assert focus_export_module._format_cost(None) == "0"
    assert focus_export_module._format_cost(object()) == "0"
    assert focus_export_module._format_currency(" eur ") == "EUR"
    assert focus_export_module._format_currency(None) == "USD"
    assert focus_export_module._tags_json([]) == ""
    assert focus_export_module._tags_json({"bad": {1, 2}}) == ""


@pytest.mark.asyncio
async def test_export_rows_falls_back_to_execute_when_stream_fails() -> None:
    service = _service_with_mock_db()
    account_id = uuid4()
    service._load_account_contexts = AsyncMock(return_value={})  # type: ignore[attr-defined]
    service.db.stream.side_effect = RuntimeError("stream unavailable")

    cost_record = SimpleNamespace(
        recorded_at=date(2026, 1, 3),
        timestamp=datetime(2026, 1, 3, 1, 0, tzinfo=timezone.utc),
        service="AmazonEC2",
        usage_type="BoxUsage:t3.micro",
        canonical_charge_category="compute",
        tags={"env": "prod"},
        ingestion_metadata=None,
        cost_usd=Decimal("12.34"),
        region="us-east-1",
    )
    account = SimpleNamespace(id=account_id, provider="aws", name="Prod AWS")
    service.db.execute.return_value = _RowsResult([(cost_record, account)])

    rows = [
        row
        async for row in service.export_rows(
            tenant_id=uuid4(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            provider="aws",
            include_preliminary=True,
        )
    ]

    assert len(rows) == 1
    assert rows[0]["ProviderName"] == "Amazon Web Services"
    assert rows[0]["BillingCurrency"] == "USD"
    assert rows[0]["Tags"] == '{"env":"prod"}'


@pytest.mark.asyncio
async def test_load_account_contexts_handles_provider_and_preliminary_paths() -> None:
    service = _service_with_mock_db()
    service.db.execute.return_value = _RowsResult([])
    service._enrich_cloud_accounts = AsyncMock()  # type: ignore[attr-defined]
    service._enrich_cloud_plus_accounts = AsyncMock()  # type: ignore[attr-defined]

    contexts = await service._load_account_contexts(
        tenant_id=uuid4(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        provider="aws",
        include_preliminary=True,
    )

    assert contexts == {}
    service.db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_cloud_accounts_updates_known_contexts_and_skips_unknown() -> None:
    service = _service_with_mock_db()
    aws_id = uuid4()
    azure_id = uuid4()
    gcp_id = uuid4()
    unknown_id = uuid4()
    contexts = {
        aws_id: FocusAccountContext(
            provider_key="aws",
            billing_account_id=str(aws_id),
            billing_account_name="aws",
            provider_name="aws",
            publisher_name="aws",
            service_provider_name="aws",
            invoice_issuer_name="aws",
        ),
        azure_id: FocusAccountContext(
            provider_key="azure",
            billing_account_id=str(azure_id),
            billing_account_name="",
            provider_name="azure",
            publisher_name="azure",
            service_provider_name="azure",
            invoice_issuer_name="azure",
        ),
        gcp_id: FocusAccountContext(
            provider_key="gcp",
            billing_account_id=str(gcp_id),
            billing_account_name="",
            provider_name="gcp",
            publisher_name="gcp",
            service_provider_name="gcp",
            invoice_issuer_name="gcp",
        ),
    }
    service.db.execute.side_effect = [
        _RowsResult([(unknown_id, "111111111111"), (aws_id, "123456789012")]),
        _RowsResult([(azure_id, "sub-123")]),
        _RowsResult([(gcp_id, "project-abc")]),
    ]

    await service._enrich_cloud_accounts(contexts, [aws_id, azure_id, gcp_id])

    assert contexts[aws_id].billing_account_id == "123456789012"
    assert contexts[azure_id].billing_account_id == "sub-123"
    assert contexts[gcp_id].billing_account_id == "project-abc"
    assert contexts[gcp_id].provider_name == "Google Cloud"


@pytest.mark.asyncio
async def test_enrich_cloud_plus_accounts_handles_unknown_provider_and_context_filter() -> None:
    service = _service_with_mock_db()
    known_id = uuid4()
    unknown_id = uuid4()
    contexts = {
        known_id: FocusAccountContext(
            provider_key="saas",
            billing_account_id=str(known_id),
            billing_account_name="SaaS Acct",
            provider_name="saas",
            publisher_name="saas",
            service_provider_name="saas",
            invoice_issuer_name="saas",
        )
    }

    await service._enrich_cloud_plus_accounts(contexts, "unknown", [known_id])
    service.db.execute.assert_not_awaited()

    service.db.execute.return_value = _RowsResult(
        [(known_id, "microsoft_365"), (unknown_id, "zoom")]
    )
    await service._enrich_cloud_plus_accounts(contexts, "saas", [known_id, unknown_id])

    assert contexts[known_id].provider_name == "Microsoft 365"
    assert contexts[known_id].billing_account_name == "SaaS Acct"


def test_row_to_focus_uses_context_fallback_for_non_cloud_records() -> None:
    service = _service_with_mock_db()
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, provider="platform", name="Ops Platform")
    cost_record = SimpleNamespace(
        recorded_at=date(2026, 2, 14),
        timestamp=None,
        service=None,
        usage_type=None,
        canonical_charge_category=None,
        region="",
        tags=[],
        ingestion_metadata={"tags": {"owner": "finops"}},
        cost_usd=Decimal("0.25"),
    )

    row = service._row_to_focus(cost_record, account, contexts={})

    assert row["ServiceName"] == "Unknown"
    assert row["ChargeCategory"] == "Usage"
    assert row["ChargeFrequency"] == "Usage-Based"
    assert row["Tags"] == '{"owner":"finops"}'
    assert row["ProviderName"] == "PLATFORM"


def test_row_to_focus_handles_non_dict_metadata_tags_and_cloud_hour_window() -> None:
    service = _service_with_mock_db()
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, provider="aws", name="AWS")
    timestamp = datetime(2026, 2, 14, 6, 30, tzinfo=timezone.utc)
    cost_record = SimpleNamespace(
        recorded_at=date(2026, 2, 14),
        timestamp=timestamp,
        service="AmazonS3",
        usage_type="Requests",
        canonical_charge_category="storage",
        region="us-east-1",
        tags=None,
        ingestion_metadata=["bad-shape"],
        cost_usd=Decimal("4.5"),
    )

    row = service._row_to_focus(cost_record, account, contexts={})

    assert row["ChargePeriodStart"] == "2026-02-14T06:30:00Z"
    assert row["ChargePeriodEnd"] == "2026-02-14T07:30:00Z"
    assert row["Tags"] == ""
