"""
FinOps Analysis Job Handler
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.background_job import BackgroundJob
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.config import get_settings
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.factory import LLMFactory


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _normalize_rows(rows: list[dict[str, Any]]) -> list[CostRecord]:
    records: list[CostRecord] = []
    for row in rows:
        raw_amount = row.get("cost_usd", 0) or 0
        amount = Decimal(str(raw_amount))
        if amount <= 0:
            continue

        amount_raw = row.get("amount_raw")
        amount_raw_decimal = (
            Decimal(str(amount_raw)) if amount_raw is not None else None
        )
        tags = row.get("tags")
        records.append(
            CostRecord(
                date=_as_datetime(row.get("timestamp")),
                amount=amount,
                amount_raw=amount_raw_decimal,
                currency=str(row.get("currency") or "USD"),
                service=str(row.get("service") or "unknown"),
                region=row.get("region"),
                usage_type=row.get("usage_type"),
                tags=tags if isinstance(tags, dict) else {},
            )
        )

    return records


class FinOpsAnalysisHandler(BaseJobHandler):
    """Handle multi-tenant FinOps analysis with normalized components."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for finops_analysis")

        tenant_uuid = UUID(str(tenant_id))
        connections: list[Any] = []
        for connection_model in (
            AWSConnection,
            AzureConnection,
            GCPConnection,
            SaaSConnection,
            LicenseConnection,
            PlatformConnection,
            HybridConnection,
        ):
            result = await db.execute(
                select(connection_model).where(
                    connection_model.tenant_id == tenant_uuid
                )
            )
            connections.extend(result.scalars().all())

        if not connections:
            return {"status": "skipped", "reason": "no_connections"}

        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        settings = get_settings()
        llm = LLMFactory.create(settings.LLM_PROVIDER)
        analyzer = FinOpsAnalyzer(llm=llm)
        analyses: List[Dict[str, Any]] = []
        analyzed_providers: set[str] = set()

        for connection in connections:
            provider = str(getattr(connection, "provider", "aws")).lower()
            try:
                adapter = AdapterFactory.get_adapter(connection)

                if provider == "aws" and hasattr(adapter, "get_daily_costs"):
                    usage_summary = await adapter.get_daily_costs(
                        start_date,
                        end_date,
                        group_by_service=True,
                    )
                else:
                    rows = await adapter.get_cost_and_usage(
                        start_dt, end_dt, granularity="DAILY"
                    )
                    records = _normalize_rows(rows)
                    if not records:
                        continue
                    total_cost = sum(
                        (record.amount for record in records), Decimal("0")
                    )
                    usage_summary = CloudUsageSummary(
                        tenant_id=str(tenant_uuid),
                        provider=provider,
                        start_date=start_date,
                        end_date=end_date,
                        total_cost=total_cost,
                        records=records,
                    )

                if not usage_summary.records:
                    continue

                llm_result = await analyzer.analyze(
                    usage_summary,
                    tenant_id=tenant_uuid,
                    db=db,
                    provider=provider,
                )
                if isinstance(llm_result, dict):
                    analyses.append(llm_result)
                analyzed_providers.add(provider)
            except Exception:
                # Keep processing remaining providers even if one fails.
                continue

        if not analyses:
            return {"status": "skipped", "reason": "no_cost_data"}

        analysis_length = sum(len(str(result)) for result in analyses)
        return {
            "status": "completed",
            "analysis_runs": len(analyses),
            "providers_analyzed": sorted(analyzed_providers),
            "analysis_length": analysis_length,
        }
