"""
Cost Reconciliation Service

Detects discrepancies between "fast" API data (Explorer) and "slow" CUR data (S3 Parquet).
Ensures financial trust by flagging deltas >1%.
"""

import csv
import hashlib
import io
import json
import structlog
from typing import Dict, Any
from uuid import UUID
from datetime import date
from decimal import Decimal
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.cloud import CostRecord, CloudAccount
from app.models.cost_audit import CostAuditLog
from app.models.invoice import ProviderInvoice

logger = structlog.get_logger()


RECON_ALERT_THRESHOLD_PCT = 1.0
SUPPORTED_RECON_PROVIDERS = {
    "aws",
    "azure",
    "gcp",
    "saas",
    "license",
    "platform",
    "hybrid",
}


class CostReconciliationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _normalize_source(source: str | None) -> str:
        source_key = (source or "unknown").strip().lower()
        if source_key in {"unknown", "", "null"}:
            return "unknown"

        if any(token in source_key for token in ("cur", "parquet", "s3")):
            return "cur"
        if any(
            token in source_key
            for token in ("explorer", "cost_explorer", "ce_api", "cost_management")
        ):
            return "explorer"
        return source_key

    @staticmethod
    def _normalize_provider(provider: str | None) -> str | None:
        if provider is None:
            return None
        provider_key = provider.strip().lower()
        if not provider_key:
            return None
        if provider_key not in SUPPORTED_RECON_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{provider}'. Supported providers: "
                f"{', '.join(sorted(SUPPORTED_RECON_PROVIDERS))}"
            )
        return provider_key

    @staticmethod
    def _normalize_cloud_plus_source(source: str | None, provider: str) -> str:
        source_key = (source or "unknown").strip().lower()
        if provider in {"saas", "license", "platform", "hybrid"}:
            if source_key in {f"{provider}_feed", "feed"}:
                return "feed"
            if source_key in {"native", f"{provider}_native"}:
                return "native"
            if source_key.startswith(f"{provider}_"):
                return "native"
            return "unknown"

        return "unknown"

    @staticmethod
    def _compute_confidence(
        total_service_count: int,
        comparable_service_count: int,
        comparable_record_count: int,
    ) -> float:
        if total_service_count <= 0 or comparable_service_count <= 0:
            return 0.0
        coverage_ratio = comparable_service_count / total_service_count
        volume_factor = min(comparable_record_count / 1000.0, 1.0)
        return round(min(1.0, 0.6 * coverage_ratio + 0.4 * volume_factor), 2)

    @staticmethod
    def _to_float(value: Any) -> float:
        return float(value or 0)

    @staticmethod
    def _to_int(value: Any) -> int:
        return int(value or 0)

    @staticmethod
    def _stable_hash(payload: Dict[str, Any]) -> str:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _render_close_package_csv(
        tenant_id: str,
        start_date: date,
        end_date: date,
        close_status: str,
        lifecycle_summary: Dict[str, Any],
        reconciliation_summary: Dict[str, Any],
        invoice_reconciliation: Dict[str, Any] | None,
        restatement_entries: list[Dict[str, Any]],
    ) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["section", "key", "value"])
        writer.writerow(["meta", "tenant_id", tenant_id])
        writer.writerow(["meta", "start_date", start_date.isoformat()])
        writer.writerow(["meta", "end_date", end_date.isoformat()])
        writer.writerow(["meta", "close_status", close_status])

        for key, value in lifecycle_summary.items():
            writer.writerow(["lifecycle", key, value])

        for key, value in reconciliation_summary.items():
            if key in {"impacted_services", "discrepancies"}:
                continue
            writer.writerow(["reconciliation", key, value])

        if isinstance(invoice_reconciliation, dict) and invoice_reconciliation:
            writer.writerow(
                [
                    "invoice_reconciliation",
                    "status",
                    invoice_reconciliation.get("status"),
                ]
            )
            writer.writerow(
                [
                    "invoice_reconciliation",
                    "threshold_percent",
                    invoice_reconciliation.get("threshold_percent"),
                ]
            )
            writer.writerow(
                [
                    "invoice_reconciliation",
                    "ledger_final_cost_usd",
                    invoice_reconciliation.get("ledger_final_cost_usd"),
                ]
            )
            if invoice_reconciliation.get("status") != "missing_invoice":
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "delta_usd",
                        invoice_reconciliation.get("delta_usd"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "absolute_delta_usd",
                        invoice_reconciliation.get("absolute_delta_usd"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "delta_percent",
                        invoice_reconciliation.get("delta_percent"),
                    ]
                )
            invoice_obj = invoice_reconciliation.get("invoice")
            if isinstance(invoice_obj, dict):
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "invoice_number",
                        invoice_obj.get("invoice_number"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "invoice_currency",
                        invoice_obj.get("currency"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "invoice_total_amount",
                        invoice_obj.get("total_amount"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "invoice_total_amount_usd",
                        invoice_obj.get("total_amount_usd"),
                    ]
                )
                writer.writerow(
                    [
                        "invoice_reconciliation",
                        "invoice_status",
                        invoice_obj.get("status"),
                    ]
                )

        writer.writerow([])
        writer.writerow(
            [
                "restatements",
                "usage_date",
                "recorded_at",
                "service",
                "region",
                "old_cost",
                "new_cost",
                "delta_usd",
                "reason",
                "cost_record_id",
                "ingestion_batch_id",
            ]
        )
        for entry in restatement_entries:
            writer.writerow(
                [
                    "restatements",
                    entry["usage_date"],
                    entry["recorded_at"],
                    entry["service"],
                    entry["region"],
                    entry["old_cost"],
                    entry["new_cost"],
                    entry["delta_usd"],
                    entry["reason"],
                    entry["cost_record_id"],
                    entry["ingestion_batch_id"],
                ]
            )
        return out.getvalue()

    @staticmethod
    def _render_restatements_csv(entries: list[Dict[str, Any]]) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "usage_date",
                "recorded_at",
                "service",
                "region",
                "old_cost",
                "new_cost",
                "delta_usd",
                "reason",
                "cost_record_id",
                "ingestion_batch_id",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    entry["usage_date"],
                    entry["recorded_at"],
                    entry["service"],
                    entry["region"],
                    entry["old_cost"],
                    entry["new_cost"],
                    entry["delta_usd"],
                    entry["reason"],
                    entry["cost_record_id"],
                    entry["ingestion_batch_id"],
                ]
            )
        return out.getvalue()

    @staticmethod
    def _render_restatement_runs_csv(runs: list[Dict[str, Any]]) -> str:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "ingestion_batch_id",
                "entry_count",
                "net_delta_usd",
                "absolute_delta_usd",
                "first_recorded_at",
                "last_recorded_at",
                "integrity_hash",
            ]
        )
        for run in runs:
            writer.writerow(
                [
                    run.get("ingestion_batch_id"),
                    run.get("entry_count"),
                    run.get("net_delta_usd"),
                    run.get("absolute_delta_usd"),
                    run.get("first_recorded_at"),
                    run.get("last_recorded_at"),
                    run.get("integrity_hash"),
                ]
            )
        return out.getvalue()

    async def get_restatement_history(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        export_csv: bool = False,
        provider: str | None = None,
    ) -> Dict[str, Any]:
        normalized_provider = self._normalize_provider(provider)
        stmt = (
            select(
                CostAuditLog.recorded_at.label("audit_recorded_at"),
                CostAuditLog.cost_record_id.label("cost_record_id"),
                CostAuditLog.old_cost.label("old_cost"),
                CostAuditLog.new_cost.label("new_cost"),
                CostAuditLog.reason.label("reason"),
                CostAuditLog.ingestion_batch_id.label("ingestion_batch_id"),
                CostRecord.service.label("service"),
                CostRecord.region.label("region"),
                CostRecord.recorded_at.label("usage_date"),
            )
            .join(
                CostRecord,
                and_(
                    CostAuditLog.cost_record_id == CostRecord.id,
                    CostAuditLog.cost_recorded_at == CostRecord.recorded_at,
                ),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
            )
        )
        if normalized_provider:
            stmt = stmt.join(
                CloudAccount, CostRecord.account_id == CloudAccount.id
            ).where(CloudAccount.provider == normalized_provider)
        result = await self.db.execute(stmt)
        rows = sorted(
            result.all(),
            key=lambda row: (
                str(getattr(row, "usage_date", "")),
                str(getattr(row, "service", "")),
                str(getattr(row, "cost_record_id", "")),
            ),
        )

        entries: list[Dict[str, Any]] = []
        net_delta = Decimal("0")
        abs_delta = Decimal("0")
        for row in rows:
            old_cost = Decimal(str(getattr(row, "old_cost", 0) or 0))
            new_cost = Decimal(str(getattr(row, "new_cost", 0) or 0))
            delta = new_cost - old_cost
            net_delta += delta
            abs_delta += abs(delta)
            usage_date_obj = getattr(row, "usage_date", None)
            audit_recorded_at = getattr(row, "audit_recorded_at", None)

            entries.append(
                {
                    "usage_date": usage_date_obj.isoformat()
                    if usage_date_obj is not None
                    else None,
                    "recorded_at": audit_recorded_at.isoformat()
                    if audit_recorded_at is not None
                    else None,
                    "service": str(getattr(row, "service", "") or "Unknown"),
                    "region": str(getattr(row, "region", "") or "Global"),
                    "old_cost": float(old_cost),
                    "new_cost": float(new_cost),
                    "delta_usd": float(delta),
                    "reason": str(getattr(row, "reason", "") or "RE-INGESTION"),
                    "cost_record_id": str(getattr(row, "cost_record_id", "") or ""),
                    "ingestion_batch_id": str(
                        getattr(row, "ingestion_batch_id", "") or ""
                    ),
                }
            )

        payload: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "provider": normalized_provider,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "restatement_count": len(entries),
            "net_delta_usd": float(net_delta),
            "absolute_delta_usd": float(abs_delta),
            "entries": entries,
        }
        if export_csv:
            payload["csv"] = self._render_restatements_csv(entries)
        return payload

    async def get_restatement_runs(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        export_csv: bool = False,
        provider: str | None = None,
    ) -> Dict[str, Any]:
        """
        Group restatement audit logs by ingestion_batch_id to produce run-level summaries.

        This provides an explicit lifecycle view of "which ingestion runs caused bill restatements"
        without storing large close artifacts in the database.
        """
        normalized_provider = self._normalize_provider(provider)
        delta_expr = CostAuditLog.new_cost - CostAuditLog.old_cost

        stmt = (
            select(
                CostAuditLog.ingestion_batch_id.label("ingestion_batch_id"),
                func.count(CostAuditLog.id).label("entry_count"),
                func.coalesce(func.sum(delta_expr), 0).label("net_delta_usd"),
                func.coalesce(func.sum(func.abs(delta_expr)), 0).label(
                    "absolute_delta_usd"
                ),
                func.min(CostAuditLog.recorded_at).label("first_recorded_at"),
                func.max(CostAuditLog.recorded_at).label("last_recorded_at"),
            )
            .join(
                CostRecord,
                and_(
                    CostAuditLog.cost_record_id == CostRecord.id,
                    CostAuditLog.cost_recorded_at == CostRecord.recorded_at,
                ),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
            )
            .group_by(CostAuditLog.ingestion_batch_id)
        )
        if normalized_provider:
            stmt = stmt.join(
                CloudAccount, CostRecord.account_id == CloudAccount.id
            ).where(CloudAccount.provider == normalized_provider)

        result = await self.db.execute(stmt)
        rows = list(result.all())
        rows.sort(
            key=lambda row: str(getattr(row, "last_recorded_at", "") or ""),
            reverse=True,
        )

        runs: list[Dict[str, Any]] = []
        for row in rows:
            ingestion_batch_id = getattr(row, "ingestion_batch_id", None)
            payload = {
                "ingestion_batch_id": str(ingestion_batch_id)
                if ingestion_batch_id
                else None,
                "entry_count": self._to_int(getattr(row, "entry_count", 0)),
                "net_delta_usd": self._to_float(getattr(row, "net_delta_usd", 0)),
                "absolute_delta_usd": self._to_float(
                    getattr(row, "absolute_delta_usd", 0)
                ),
                "first_recorded_at": (
                    getattr(row, "first_recorded_at").isoformat()
                    if getattr(row, "first_recorded_at", None) is not None
                    else None
                ),
                "last_recorded_at": (
                    getattr(row, "last_recorded_at").isoformat()
                    if getattr(row, "last_recorded_at", None) is not None
                    else None
                ),
            }
            payload["integrity_hash"] = self._stable_hash(payload)
            runs.append(payload)

        response: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "provider": normalized_provider,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "run_count": len(runs),
            "runs": runs,
        }
        if export_csv:
            response["csv"] = self._render_restatement_runs_csv(runs)
        return response

    async def generate_close_package(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        enforce_finalized: bool = True,
        provider: str | None = None,
        max_restatement_entries: int | None = None,
    ) -> Dict[str, Any]:
        normalized_provider = self._normalize_provider(provider)
        lifecycle_stmt = select(
            func.count(CostRecord.id).label("total_records"),
            func.count(CostRecord.id)
            .filter(CostRecord.cost_status == "PRELIMINARY")
            .label("preliminary_records"),
            func.count(CostRecord.id)
            .filter(CostRecord.cost_status == "FINAL")
            .label("final_records"),
            func.coalesce(func.sum(CostRecord.cost_usd), 0).label("total_cost_usd"),
            func.coalesce(
                func.sum(CostRecord.cost_usd).filter(
                    CostRecord.cost_status == "PRELIMINARY"
                ),
                0,
            ).label("preliminary_cost_usd"),
            func.coalesce(
                func.sum(CostRecord.cost_usd).filter(CostRecord.cost_status == "FINAL"),
                0,
            ).label("final_cost_usd"),
        ).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= start_date,
            CostRecord.recorded_at <= end_date,
        )
        if normalized_provider:
            lifecycle_stmt = lifecycle_stmt.join(
                CloudAccount, CostRecord.account_id == CloudAccount.id
            ).where(CloudAccount.provider == normalized_provider)
        lifecycle_result = await self.db.execute(lifecycle_stmt)
        lifecycle_row = lifecycle_result.one()

        lifecycle_summary = {
            "total_records": self._to_int(getattr(lifecycle_row, "total_records", 0)),
            "preliminary_records": self._to_int(
                getattr(lifecycle_row, "preliminary_records", 0)
            ),
            "final_records": self._to_int(getattr(lifecycle_row, "final_records", 0)),
            "total_cost_usd": self._to_float(
                getattr(lifecycle_row, "total_cost_usd", 0)
            ),
            "preliminary_cost_usd": self._to_float(
                getattr(lifecycle_row, "preliminary_cost_usd", 0)
            ),
            "final_cost_usd": self._to_float(
                getattr(lifecycle_row, "final_cost_usd", 0)
            ),
        }
        preliminary_records = lifecycle_summary["preliminary_records"]
        close_status = (
            "ready" if preliminary_records == 0 else "blocked_preliminary_data"
        )
        if enforce_finalized and preliminary_records > 0:
            raise ValueError(
                "Cannot generate final close package while preliminary records exist in the selected period."
            )

        reconciliation_summary = await self.compare_explorer_vs_cur(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            provider=normalized_provider,
        )

        invoice_summary = None
        if normalized_provider:
            invoice_summary = await self.get_invoice_reconciliation_summary(
                tenant_id=tenant_id,
                provider=normalized_provider,
                start_date=start_date,
                end_date=end_date,
                ledger_final_cost_usd=float(
                    lifecycle_summary.get("final_cost_usd") or 0.0
                ),
            )
        restatement_payload = await self.get_restatement_history(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            export_csv=False,
            provider=normalized_provider,
        )
        restatement_entries = list(restatement_payload.get("entries") or [])
        restatement_total = len(restatement_entries)
        restatement_truncated = False
        if isinstance(max_restatement_entries, int) and max_restatement_entries >= 0:
            if restatement_total > max_restatement_entries:
                restatement_truncated = True
                restatement_entries = restatement_entries[:max_restatement_entries]

        package_core: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "provider": normalized_provider,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "close_status": close_status,
            "lifecycle": lifecycle_summary,
            "reconciliation": reconciliation_summary,
            "invoice_reconciliation": invoice_summary,
            "restatements": {
                "count": restatement_payload["restatement_count"],
                "included_count": len(restatement_entries),
                "truncated": restatement_truncated,
                "net_delta_usd": restatement_payload["net_delta_usd"],
                "absolute_delta_usd": restatement_payload["absolute_delta_usd"],
                "entries": restatement_entries,
            },
            "package_version": "reconciliation-v3",
        }
        package_hash = self._stable_hash(package_core)
        close_csv = self._render_close_package_csv(
            tenant_id=str(tenant_id),
            start_date=start_date,
            end_date=end_date,
            close_status=close_status,
            lifecycle_summary=lifecycle_summary,
            reconciliation_summary=reconciliation_summary,
            invoice_reconciliation=invoice_summary,
            restatement_entries=restatement_entries,
        )
        package_core["integrity_hash"] = package_hash
        package_core["csv"] = close_csv
        return package_core

    async def list_invoices(
        self,
        tenant_id: UUID,
        provider: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ProviderInvoice]:
        normalized_provider = self._normalize_provider(provider) if provider else None
        stmt = select(ProviderInvoice).where(ProviderInvoice.tenant_id == tenant_id)
        if normalized_provider:
            stmt = stmt.where(ProviderInvoice.provider == normalized_provider)
        if start_date:
            stmt = stmt.where(ProviderInvoice.period_start >= start_date)
        if end_date:
            stmt = stmt.where(ProviderInvoice.period_end <= end_date)
        stmt = stmt.order_by(
            ProviderInvoice.period_start.desc(), ProviderInvoice.provider.asc()
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_invoice(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
    ) -> ProviderInvoice | None:
        result = await self.db.execute(
            select(ProviderInvoice).where(
                ProviderInvoice.tenant_id == tenant_id,
                ProviderInvoice.id == invoice_id,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_invoice(
        self,
        tenant_id: UUID,
        *,
        provider: str,
        start_date: date,
        end_date: date,
        currency: str,
        total_amount: Decimal,
        invoice_number: str | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> ProviderInvoice:
        normalized_provider = self._normalize_provider(provider)
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        currency_key = (currency or "USD").strip().upper() or "USD"
        total_amount_dec = Decimal(str(total_amount or 0))
        total_amount_usd = await self._invoice_total_to_usd(
            total_amount_dec, currency_key
        )

        existing_result = await self.db.execute(
            select(ProviderInvoice).where(
                ProviderInvoice.tenant_id == tenant_id,
                ProviderInvoice.provider == normalized_provider,
                ProviderInvoice.period_start == start_date,
                ProviderInvoice.period_end == end_date,
            )
        )
        invoice = existing_result.scalar_one_or_none()

        if invoice is None:
            invoice = ProviderInvoice(
                tenant_id=tenant_id,
                provider=normalized_provider,
                period_start=start_date,
                period_end=end_date,
            )
            self.db.add(invoice)

        invoice.invoice_number = invoice_number
        invoice.currency = currency_key
        invoice.total_amount = total_amount_dec
        invoice.total_amount_usd = total_amount_usd
        if status:
            invoice.status = str(status).strip().lower()
        if notes is not None:
            invoice.notes = notes

        await self.db.commit()
        await self.db.refresh(invoice)
        return invoice

    async def delete_invoice(self, tenant_id: UUID, invoice_id: UUID) -> bool:
        invoice = await self.get_invoice(tenant_id, invoice_id)
        if invoice is None:
            return False
        await self.db.delete(invoice)
        await self.db.commit()
        return True

    async def update_invoice_status(
        self,
        tenant_id: UUID,
        invoice_id: UUID,
        *,
        status: str,
        notes: str | None = None,
    ) -> ProviderInvoice | None:
        invoice = await self.get_invoice(tenant_id, invoice_id)
        if invoice is None:
            return None
        invoice.status = str(status).strip().lower()
        if notes is not None:
            invoice.notes = notes
        await self.db.commit()
        await self.db.refresh(invoice)
        return invoice

    async def _invoice_total_to_usd(self, amount: Decimal, currency: str) -> Decimal:
        """
        Convert invoice total to USD without relying on external APIs.

        We prefer deterministic DB-backed exchange rates. If currency != USD and no exchange rate is
        present, we fail fast to avoid silently incorrect reconciliation.
        """
        currency_key = (currency or "USD").strip().upper()
        if currency_key == "USD":
            return amount

        # DB-backed exchange rates (pricing.exchange_rates) are preferred for finance-grade close.
        try:
            from app.models.pricing import ExchangeRate
        except Exception:
            raise ValueError(
                "Exchange rate model unavailable; use USD currency for invoice totals."
            )

        rate_row = (
            await self.db.execute(
                select(ExchangeRate.rate).where(
                    ExchangeRate.from_currency == "USD",
                    ExchangeRate.to_currency == currency_key,
                )
            )
        ).first()
        if rate_row and rate_row[0]:
            rate_usd_to_currency = Decimal(str(rate_row[0]))
            if rate_usd_to_currency <= 0:
                raise ValueError(f"Invalid exchange rate for USD->{currency_key}.")
            return amount / rate_usd_to_currency

        inverse_row = (
            await self.db.execute(
                select(ExchangeRate.rate).where(
                    ExchangeRate.from_currency == currency_key,
                    ExchangeRate.to_currency == "USD",
                )
            )
        ).first()
        if inverse_row and inverse_row[0]:
            rate_currency_to_usd = Decimal(str(inverse_row[0]))
            if rate_currency_to_usd <= 0:
                raise ValueError(f"Invalid exchange rate for {currency_key}->USD.")
            return amount * rate_currency_to_usd

        raise ValueError(
            f"Missing exchange rate for invoice currency {currency_key}. "
            "Seed exchange_rates or provide invoice totals in USD."
        )

    async def get_invoice_reconciliation_summary(
        self,
        *,
        tenant_id: UUID,
        provider: str,
        start_date: date,
        end_date: date,
        ledger_final_cost_usd: float,
        threshold_percent: float = 1.0,
    ) -> Dict[str, Any]:
        normalized_provider = self._normalize_provider(provider)
        invoice_result = await self.db.execute(
            select(ProviderInvoice).where(
                ProviderInvoice.tenant_id == tenant_id,
                ProviderInvoice.provider == normalized_provider,
                ProviderInvoice.period_start == start_date,
                ProviderInvoice.period_end == end_date,
            )
        )
        invoice = invoice_result.scalar_one_or_none()
        if invoice is None:
            return {
                "status": "missing_invoice",
                "provider": normalized_provider,
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
                "ledger_final_cost_usd": float(ledger_final_cost_usd or 0.0),
                "threshold_percent": threshold_percent,
            }

        invoice_usd = float(invoice.total_amount_usd or 0)
        ledger_usd = float(ledger_final_cost_usd or 0.0)
        delta_usd = ledger_usd - invoice_usd
        abs_delta_usd = abs(delta_usd)
        denominator = invoice_usd if invoice_usd > 0 else max(ledger_usd, 1e-9)
        delta_percent = (
            (abs_delta_usd / denominator) * 100.0 if denominator > 0 else 0.0
        )
        matches = delta_percent <= float(threshold_percent or 0.0)

        payload = {
            "status": "match" if matches else "mismatch",
            "provider": normalized_provider,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "threshold_percent": float(threshold_percent),
            "invoice": {
                "id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "currency": invoice.currency,
                "total_amount": float(invoice.total_amount or 0),
                "total_amount_usd": float(invoice.total_amount_usd or 0),
                "status": invoice.status,
                "notes": invoice.notes,
                "updated_at": invoice.updated_at.isoformat()
                if invoice.updated_at
                else None,
            },
            "ledger_final_cost_usd": float(ledger_usd),
            "delta_usd": float(delta_usd),
            "absolute_delta_usd": float(abs_delta_usd),
            "delta_percent": float(round(delta_percent, 4)),
        }
        payload["integrity_hash"] = self._stable_hash(payload)
        return payload

    async def compare_explorer_vs_cur(
        self,
        tenant_id: UUID,
        start_date: date,
        end_date: date,
        alert_threshold_pct: float = RECON_ALERT_THRESHOLD_PCT,
        provider: str | None = None,
    ) -> Dict[str, Any]:
        """
        Compare Explorer and CUR cost views by service for reconciliation.
        Uses ingestion metadata source markers to derive source buckets.
        """
        normalized_provider = self._normalize_provider(provider)
        source_expr = func.coalesce(
            func.lower(CostRecord.ingestion_metadata["source_adapter"].as_string()),
            "unknown",
        )
        stmt = (
            select(
                CostRecord.service.label("service"),
                source_expr.label("source_adapter"),
                func.sum(CostRecord.cost_usd).label("total_cost"),
                func.count(CostRecord.id).label("record_count"),
            )
            .where(
                CostRecord.tenant_id == tenant_id,
                CostRecord.recorded_at >= start_date,
                CostRecord.recorded_at <= end_date,
            )
            .group_by(CostRecord.service, source_expr)
        )
        if normalized_provider:
            stmt = stmt.join(
                CloudAccount, CostRecord.account_id == CloudAccount.id
            ).where(CloudAccount.provider == normalized_provider)

        result = await self.db.execute(stmt)
        rows = result.all()

        total_records = 0
        total_cost = 0.0
        by_service: dict[str, dict[str, float]] = {}
        by_service_records: dict[str, dict[str, int]] = {}

        comparison_basis = "explorer_vs_cur"
        expected_primary_source = "cur"
        expected_secondary_source = "explorer"
        if normalized_provider in {"saas", "license", "platform", "hybrid"}:
            comparison_basis = "native_vs_feed"
            expected_primary_source = "native"
            expected_secondary_source = "feed"

        for row in rows:
            service_name = str(getattr(row, "service", "") or "Unknown")
            if normalized_provider in {"saas", "license", "platform", "hybrid"}:
                source_name = self._normalize_cloud_plus_source(
                    getattr(row, "source_adapter", None),
                    normalized_provider,
                )
            else:
                source_name = self._normalize_source(
                    getattr(row, "source_adapter", None)
                )
            row_cost = float(getattr(row, "total_cost", 0) or 0)
            row_records = int(getattr(row, "record_count", 0) or 0)

            total_records += row_records
            total_cost += row_cost

            by_service.setdefault(service_name, {})
            by_service_records.setdefault(service_name, {})

            by_service[service_name][source_name] = (
                by_service[service_name].get(source_name, 0.0) + row_cost
            )
            by_service_records[service_name][source_name] = (
                by_service_records[service_name].get(source_name, 0) + row_records
            )

        impacted_services: list[dict[str, Any]] = []
        total_cur = 0.0
        total_explorer = 0.0
        comparable_record_count = 0

        for service_name, sources in by_service.items():
            if (
                expected_primary_source not in sources
                or expected_secondary_source not in sources
            ):
                continue

            primary_cost = float(sources[expected_primary_source])
            secondary_cost = float(sources[expected_secondary_source])
            delta_usd = secondary_cost - primary_cost
            denominator = (
                abs(primary_cost)
                if abs(primary_cost) > 0
                else max(abs(secondary_cost), 1.0)
            )
            discrepancy_pct = abs(delta_usd) / denominator * 100

            total_cur += primary_cost
            total_explorer += secondary_cost
            comparable_record_count += by_service_records[service_name].get(
                expected_primary_source, 0
            ) + by_service_records[service_name].get(expected_secondary_source, 0)

            payload: dict[str, Any] = {
                "service": service_name,
                "delta_usd": round(delta_usd, 6),
                "discrepancy_percentage": round(discrepancy_pct, 4),
            }
            if comparison_basis == "native_vs_feed":
                payload["native_cost"] = round(primary_cost, 6)
                payload["feed_cost"] = round(secondary_cost, 6)
            else:
                payload["cur_cost"] = round(primary_cost, 6)
                payload["explorer_cost"] = round(secondary_cost, 6)
            impacted_services.append(payload)

        comparable_services = len(impacted_services)
        if comparable_services > 0:
            overall_denominator = (
                abs(total_cur) if abs(total_cur) > 0 else max(abs(total_explorer), 1.0)
            )
            overall_discrepancy_pct = (
                abs(total_explorer - total_cur) / overall_denominator * 100
            )
            status = (
                "warning"
                if overall_discrepancy_pct > alert_threshold_pct
                else "healthy"
            )
        else:
            overall_discrepancy_pct = 0.0
            status = "no_comparable_data"

        confidence = self._compute_confidence(
            total_service_count=len(by_service),
            comparable_service_count=comparable_services,
            comparable_record_count=comparable_record_count,
        )

        threshold_discrepancies = [
            service
            for service in impacted_services
            if service["discrepancy_percentage"] > alert_threshold_pct
        ]
        alert_triggered = False
        alert_error: str | None = None

        if overall_discrepancy_pct > alert_threshold_pct and comparable_services > 0:
            from app.shared.core.notifications import NotificationDispatcher

            try:
                await NotificationDispatcher.send_alert(
                    title=f"Cost reconciliation variance {overall_discrepancy_pct:.2f}% (tenant {tenant_id})",
                    message=(
                        f"Reconciliation variance exceeded {alert_threshold_pct:.2f}% "
                        f"for {start_date} to {end_date}. "
                        f"Impacted services: {', '.join(s['service'] for s in threshold_discrepancies[:5]) or 'n/a'}."
                    ),
                    severity="warning",
                    tenant_id=str(tenant_id),
                    db=self.db,
                )
                alert_triggered = True
            except Exception as exc:  # pragma: no cover - alerting should never break reconciliation response
                alert_error = str(exc)
                logger.warning(
                    "cost_reconciliation_alert_failed",
                    tenant_id=str(tenant_id),
                    error=alert_error,
                )

        summary: Dict[str, Any] = {
            "tenant_id": str(tenant_id),
            "provider_scope": normalized_provider or "all",
            "period": f"{start_date} to {end_date}",
            "comparison_basis": comparison_basis,
            "status": status,
            "total_records": total_records,
            "total_cost": round(total_cost, 6),
            "threshold_percentage": alert_threshold_pct,
            "discrepancy_percentage": round(overall_discrepancy_pct, 4),
            "confidence": confidence,
            "impacted_services": impacted_services,
            "discrepancies": threshold_discrepancies,
            "source_totals": {
                expected_secondary_source: round(total_explorer, 6),
                expected_primary_source: round(total_cur, 6),
            },
            "alert_triggered": alert_triggered,
        }

        if alert_error:
            summary["alert_error"] = alert_error

        logger.info(
            "cost_reconciliation_summary_generated",
            tenant_id=str(tenant_id),
            cost=summary["total_cost"],
            discrepancy_percentage=summary["discrepancy_percentage"],
            status=status,
            confidence=confidence,
        )

        return summary
