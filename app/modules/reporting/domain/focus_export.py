from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.cloud import CloudAccount, CostRecord
from app.models.gcp_connection import GCPConnection
from app.models.hybrid_connection import HybridConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.saas_connection import SaaSConnection

logger = structlog.get_logger()

# FOCUS 1.3 core export: subset that is both high-value and fully derivable from our normalized ledger
# without pretending to include SKU/unit-price fields we do not store yet.
FOCUS_V13_CORE_COLUMNS: list[str] = [
    "BilledCost",
    "BillingAccountId",
    "BillingAccountName",
    "BillingCurrency",
    "BillingPeriodStart",
    "BillingPeriodEnd",
    "ChargeCategory",
    "ChargeClass",
    "ChargeDescription",
    "ChargeFrequency",
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "ContractedCost",
    "EffectiveCost",
    "InvoiceIssuerName",
    "ListCost",
    "ProviderName",
    "PublisherName",
    "RegionId",
    "RegionName",
    "ServiceProviderName",
    "ServiceCategory",
    "ServiceSubcategory",
    "ServiceName",
    "Tags",
]


_CLOUD_PROVIDER_DISPLAY = {
    "aws": "Amazon Web Services",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud",
}

_VENDOR_DISPLAY_OVERRIDES = {
    "microsoft_365": "Microsoft 365",
    "office365": "Microsoft 365",
    "m365": "Microsoft 365",
}

_CANONICAL_TO_SERVICE_CATEGORY = {
    "compute": "Compute",
    "storage": "Storage",
    "network": "Networking",
    "database": "Databases",
}


@dataclass(frozen=True)
class FocusAccountContext:
    provider_key: str
    billing_account_id: str
    billing_account_name: str
    provider_name: str
    publisher_name: str
    service_provider_name: str
    invoice_issuer_name: str


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _focus_datetime(dt: datetime) -> str:
    # RFC 3339 / ISO 8601 with Z suffix (timezone-agnostic and stable in CSV).
    return _as_utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")


def _month_start(day: date) -> datetime:
    return datetime(day.year, day.month, 1, tzinfo=timezone.utc)


def _next_month_start(day: date) -> datetime:
    if day.month == 12:
        return datetime(day.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(day.year, day.month + 1, 1, tzinfo=timezone.utc)


def _humanize_vendor(vendor: str | None) -> str | None:
    if not isinstance(vendor, str):
        return None
    key = vendor.strip().lower()
    if not key:
        return None
    if key in _VENDOR_DISPLAY_OVERRIDES:
        return _VENDOR_DISPLAY_OVERRIDES[key]
    return " ".join(
        part.capitalize() for part in key.replace("_", " ").replace("-", " ").split()
    )


def _service_provider_display(provider_key: str, vendor: str | None = None) -> str:
    vendor_display = _humanize_vendor(vendor)
    if vendor_display:
        return vendor_display
    return _CLOUD_PROVIDER_DISPLAY.get(
        provider_key, provider_key.upper() if provider_key else "Unknown"
    )


def _focus_service_category(canonical_category: str | None) -> str:
    key = (canonical_category or "").strip().lower()
    return _CANONICAL_TO_SERVICE_CATEGORY.get(key, "Other")


def _focus_service_subcategory(service_category: str) -> str:
    # FOCUS allows explicit "Other (...)" subcategories per ServiceCategory.
    normalized = service_category.strip() or "Other"
    return f"Other ({normalized})"


def _focus_charge_category(service: str | None, usage_type: str | None) -> str:
    combined = f"{service or ''} {usage_type or ''}".strip().lower()
    if "tax" in combined:
        return "Tax"
    if "credit" in combined or "refund" in combined:
        return "Credit"
    if any(
        token in combined
        for token in ("support", "adjust", "adjustment", "fee", "marketplace")
    ):
        return "Adjustment"
    return "Usage"


def _focus_charge_frequency(charge_category: str) -> str:
    normalized = (charge_category or "").strip()
    if normalized in {"Usage", "Tax"}:
        return "Usage-Based"
    return "One-Time"


def _format_cost(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return format(value, "f")
    try:
        return format(Decimal(str(value)), "f")
    except Exception:
        return "0"


def _format_currency(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "USD"
    return value.strip().upper()


def _tags_json(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    # Stable JSON for diffs and deterministic exports.
    try:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    except Exception:
        return ""


class FocusV13ExportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def export_rows(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: str | None = None,
        include_preliminary: bool = False,
    ) -> AsyncIterator[dict[str, str]]:
        contexts = await self._load_account_contexts(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            include_preliminary=include_preliminary,
        )

        filters: list[Any] = [
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= start_date,
            CostRecord.recorded_at <= end_date,
        ]
        if not include_preliminary:
            filters.append(CostRecord.cost_status == "FINAL")
        if provider:
            filters.append(CloudAccount.provider == provider)

        stmt = (
            select(CostRecord, CloudAccount)
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(*filters)
            .order_by(CostRecord.recorded_at.asc(), CostRecord.timestamp.asc())
            .execution_options(stream_results=True)
        )

        # Use streaming where supported; SQLite in tests still works with execute().
        try:
            result = await self.db.stream(stmt)
            async for row in result:
                cost_record, account = row
                yield self._row_to_focus(cost_record, account, contexts)
            return
        except Exception:
            logger.debug("focus_export_stream_fallback_to_execute")

        sync_result = await self.db.execute(stmt)
        for cost_record, account in sync_result:
            yield self._row_to_focus(cost_record, account, contexts)

    async def _load_account_contexts(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        provider: str | None,
        include_preliminary: bool,
    ) -> dict[UUID, FocusAccountContext]:
        filters: list[Any] = [
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= start_date,
            CostRecord.recorded_at <= end_date,
        ]
        if not include_preliminary:
            filters.append(CostRecord.cost_status == "FINAL")
        if provider:
            filters.append(CloudAccount.provider == provider)

        stmt = (
            select(CloudAccount.id, CloudAccount.provider, CloudAccount.name)
            .join(CostRecord, CostRecord.account_id == CloudAccount.id)
            .where(*filters)
            .distinct()
        )
        rows = (await self.db.execute(stmt)).all()

        contexts: dict[UUID, FocusAccountContext] = {}
        ids_by_provider: dict[str, list[UUID]] = {}
        for account_id, provider_key, name in rows:
            provider_key = str(provider_key or "").strip().lower()
            display = _service_provider_display(provider_key)
            contexts[account_id] = FocusAccountContext(
                provider_key=provider_key,
                billing_account_id=str(account_id),
                billing_account_name=str(name or ""),
                provider_name=display,
                publisher_name=display,
                service_provider_name=display,
                invoice_issuer_name=display,
            )
            ids_by_provider.setdefault(provider_key, []).append(account_id)

        # Enrich with provider-native identifiers and Cloud+ vendor names.
        await self._enrich_cloud_accounts(contexts, ids_by_provider.get("aws", []))
        await self._enrich_cloud_accounts(contexts, ids_by_provider.get("azure", []))
        await self._enrich_cloud_accounts(contexts, ids_by_provider.get("gcp", []))
        await self._enrich_cloud_plus_accounts(
            contexts, "saas", ids_by_provider.get("saas", [])
        )
        await self._enrich_cloud_plus_accounts(
            contexts, "license", ids_by_provider.get("license", [])
        )
        await self._enrich_cloud_plus_accounts(
            contexts, "platform", ids_by_provider.get("platform", [])
        )
        await self._enrich_cloud_plus_accounts(
            contexts, "hybrid", ids_by_provider.get("hybrid", [])
        )

        return contexts

    async def _enrich_cloud_accounts(
        self,
        contexts: dict[UUID, FocusAccountContext],
        account_ids: list[UUID],
    ) -> None:
        if not account_ids:
            return

        # Note: each connection model stores its provider-native identifier in a different field.
        # We update BillingAccountId so exports can round-trip to provider invoices.
        aws_rows = (
            await self.db.execute(
                select(AWSConnection.id, AWSConnection.aws_account_id).where(
                    AWSConnection.id.in_(account_ids)
                )
            )
        ).all()
        for conn_id, aws_account_id in aws_rows:
            ctx = contexts.get(conn_id)
            if not ctx:
                continue
            display = _CLOUD_PROVIDER_DISPLAY["aws"]
            contexts[conn_id] = FocusAccountContext(
                provider_key=ctx.provider_key,
                billing_account_id=str(aws_account_id),
                billing_account_name=f"AWS {aws_account_id}",
                provider_name=display,
                publisher_name=display,
                service_provider_name=display,
                invoice_issuer_name=display,
            )

        azure_rows = (
            await self.db.execute(
                select(AzureConnection.id, AzureConnection.subscription_id).where(
                    AzureConnection.id.in_(account_ids)
                )
            )
        ).all()
        for conn_id, subscription_id in azure_rows:
            ctx = contexts.get(conn_id)
            if not ctx:
                continue
            display = _CLOUD_PROVIDER_DISPLAY["azure"]
            contexts[conn_id] = FocusAccountContext(
                provider_key=ctx.provider_key,
                billing_account_id=str(subscription_id),
                billing_account_name=ctx.billing_account_name or str(subscription_id),
                provider_name=display,
                publisher_name=display,
                service_provider_name=display,
                invoice_issuer_name=display,
            )

        gcp_rows = (
            await self.db.execute(
                select(GCPConnection.id, GCPConnection.project_id).where(
                    GCPConnection.id.in_(account_ids)
                )
            )
        ).all()
        for conn_id, project_id in gcp_rows:
            ctx = contexts.get(conn_id)
            if not ctx:
                continue
            display = _CLOUD_PROVIDER_DISPLAY["gcp"]
            contexts[conn_id] = FocusAccountContext(
                provider_key=ctx.provider_key,
                billing_account_id=str(project_id),
                billing_account_name=ctx.billing_account_name or str(project_id),
                provider_name=display,
                publisher_name=display,
                service_provider_name=display,
                invoice_issuer_name=display,
            )

    async def _enrich_cloud_plus_accounts(
        self,
        contexts: dict[UUID, FocusAccountContext],
        provider_key: str,
        account_ids: list[UUID],
    ) -> None:
        if not account_ids:
            return

        model = {
            "saas": SaaSConnection,
            "license": LicenseConnection,
            "platform": PlatformConnection,
            "hybrid": HybridConnection,
        }.get(provider_key)
        if model is None:
            return

        sync_result = await self.db.execute(
            select(getattr(model, "id"), getattr(model, "vendor")).where(
                getattr(model, "id").in_(account_ids)
            )
        )
        for conn_id, vendor in sync_result.all():
            ctx = contexts.get(conn_id)
            if not ctx:
                continue
            issuer = _service_provider_display(
                provider_key, str(vendor) if vendor else None
            )
            contexts[conn_id] = FocusAccountContext(
                provider_key=ctx.provider_key,
                billing_account_id=str(conn_id),
                billing_account_name=ctx.billing_account_name,
                provider_name=issuer,
                publisher_name=issuer,
                service_provider_name=issuer,
                invoice_issuer_name=issuer,
            )

    def _row_to_focus(
        self,
        cost_record: CostRecord,
        account: CloudAccount,
        contexts: dict[UUID, FocusAccountContext],
    ) -> dict[str, str]:
        recorded_day = getattr(cost_record, "recorded_at", None) or date.today()
        billing_start = _month_start(recorded_day)
        billing_end = _next_month_start(recorded_day)

        provider_key = str(getattr(account, "provider", "") or "").strip().lower()
        charge_start: datetime
        charge_end: datetime
        ts = getattr(cost_record, "timestamp", None)
        if isinstance(ts, datetime):
            ts = _as_utc(ts)
        if provider_key in {"aws", "azure", "gcp"} and isinstance(ts, datetime):
            charge_start = ts
            charge_end = ts + timedelta(hours=1)
        else:
            charge_start = datetime.combine(recorded_day, time.min, tzinfo=timezone.utc)
            charge_end = charge_start + timedelta(days=1)

        service = getattr(cost_record, "service", None)
        usage_type = getattr(cost_record, "usage_type", None)
        charge_category = _focus_charge_category(service, usage_type)
        service_category = _focus_service_category(
            getattr(cost_record, "canonical_charge_category", None)
        )
        service_subcategory = _focus_service_subcategory(service_category)

        raw_tags = getattr(cost_record, "tags", None)
        if not isinstance(raw_tags, dict) or not raw_tags:
            meta = getattr(cost_record, "ingestion_metadata", None)
            if isinstance(meta, dict):
                raw_tags = meta.get("tags")

        ctx = contexts.get(account.id)
        if ctx is None:
            display = _service_provider_display(provider_key)
            ctx = FocusAccountContext(
                provider_key=provider_key,
                billing_account_id=str(account.id),
                billing_account_name=str(getattr(account, "name", "") or ""),
                provider_name=display,
                publisher_name=display,
                service_provider_name=display,
                invoice_issuer_name=display,
            )

        region_value = str(getattr(cost_record, "region", "") or "").strip()
        cost_value = _format_cost(getattr(cost_record, "cost_usd", None))
        # Our ledger stores `cost_usd` in USD. For exports, keep currency aligned with the cost value.
        currency_value = "USD"

        focus_row = {
            "BilledCost": cost_value,
            "BillingAccountId": ctx.billing_account_id,
            "BillingAccountName": ctx.billing_account_name,
            "BillingCurrency": currency_value,
            "BillingPeriodStart": _focus_datetime(billing_start),
            "BillingPeriodEnd": _focus_datetime(billing_end),
            "ChargeCategory": charge_category,
            "ChargeClass": "Regular",
            "ChargeDescription": str(usage_type or service or "").strip(),
            "ChargeFrequency": _focus_charge_frequency(charge_category),
            "ChargePeriodStart": _focus_datetime(charge_start),
            "ChargePeriodEnd": _focus_datetime(charge_end),
            "ContractedCost": cost_value,
            "EffectiveCost": cost_value,
            "InvoiceIssuerName": ctx.invoice_issuer_name,
            "ListCost": cost_value,
            "ProviderName": ctx.provider_name,
            "PublisherName": ctx.publisher_name,
            "RegionId": region_value,
            "RegionName": region_value,
            "ServiceProviderName": ctx.service_provider_name,
            "ServiceCategory": service_category,
            "ServiceSubcategory": service_subcategory,
            "ServiceName": str(service or "Unknown").strip() or "Unknown",
            "Tags": _tags_json(raw_tags),
        }

        # Ensure stable presence for all expected columns (avoid accidental KeyError).
        return {col: str(focus_row.get(col, "")) for col in FOCUS_V13_CORE_COLUMNS}
