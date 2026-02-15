"""
Cost Management Job Handlers
"""

import structlog
from typing import Any, AsyncGenerator, AsyncIterator, Dict
from datetime import datetime, timezone, timedelta, date, time
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.shared.core.async_utils import maybe_await

logger = structlog.get_logger()


def _require_tenant_id(job: BackgroundJob) -> UUID:
    if job.tenant_id is None:
        raise ValueError("tenant_id required")
    return job.tenant_id


def _require_iso_date(payload: dict[str, Any], key: str) -> date:
    raw_value = payload.get(key)
    if not isinstance(raw_value, str):
        raise ValueError(f"{key} must be an ISO date string")
    return date.fromisoformat(raw_value)


def _serialize_anomaly(item: Any) -> dict[str, Any]:
    return {
        "day": item.day.isoformat(),
        "provider": item.provider,
        "account_id": str(item.account_id),
        "account_name": item.account_name,
        "service": item.service,
        "actual_cost_usd": float(item.actual_cost_usd),
        "expected_cost_usd": float(item.expected_cost_usd),
        "delta_cost_usd": float(item.delta_cost_usd),
        "percent_change": item.percent_change,
        "kind": item.kind,
        "probable_cause": item.probable_cause,
        "confidence": item.confidence,
        "severity": item.severity,
    }


class CostIngestionHandler(BaseJobHandler):
    """Processes high-fidelity cost ingestion for cloud accounts (Multi-Cloud)."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.shared.adapters.factory import AdapterFactory
        from app.modules.reporting.domain.persistence import CostPersistenceService
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        from app.models.saas_connection import SaaSConnection
        from app.models.license_connection import LicenseConnection
        from app.models.platform_connection import PlatformConnection
        from app.models.hybrid_connection import HybridConnection
        from app.models.cloud import CloudAccount
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        tenant_id = _require_tenant_id(job)
        payload = job.payload or {}
        payload_start = payload.get("start_date")
        payload_end = payload.get("end_date")
        if (payload_start is None) ^ (payload_end is None):
            raise ValueError(
                "Both start_date and end_date must be provided for backfill windows"
            )
        custom_window = payload_start is not None and payload_end is not None
        if custom_window:
            range_start = _require_iso_date(payload, "start_date")
            range_end = _require_iso_date(payload, "end_date")
            start_date = datetime.combine(range_start, time.min, tzinfo=timezone.utc)
            end_date = datetime.combine(range_end, time.max, tzinfo=timezone.utc)
        else:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=7)
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")

        # 1. Get Connections from all providers
        connections: list[Any] = []

        # AWS
        aws_result = await db.execute(
            select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
        )
        connections.extend(aws_result.scalars().all())
        # Azure
        azure_result = await db.execute(
            select(AzureConnection).where(AzureConnection.tenant_id == tenant_id)
        )
        connections.extend(azure_result.scalars().all())
        # GCP
        gcp_result = await db.execute(
            select(GCPConnection).where(GCPConnection.tenant_id == tenant_id)
        )
        connections.extend(gcp_result.scalars().all())
        # SaaS
        saas_result = await db.execute(
            select(SaaSConnection).where(SaaSConnection.tenant_id == tenant_id)
        )
        connections.extend(saas_result.scalars().all())
        # License
        license_result = await db.execute(
            select(LicenseConnection).where(LicenseConnection.tenant_id == tenant_id)
        )
        connections.extend(license_result.scalars().all())
        # Platform
        platform_result = await db.execute(
            select(PlatformConnection).where(PlatformConnection.tenant_id == tenant_id)
        )
        connections.extend(platform_result.scalars().all())
        # Hybrid
        hybrid_result = await db.execute(
            select(HybridConnection).where(HybridConnection.tenant_id == tenant_id)
        )
        connections.extend(hybrid_result.scalars().all())

        if not connections:
            return {"status": "skipped", "reason": "no_active_connections"}

        persistence = CostPersistenceService(db)
        results = []
        total_records_ingested = 0

        for conn in connections:
            stmt = (
                pg_insert(CloudAccount)
                .values(
                    id=conn.id,
                    tenant_id=conn.tenant_id,
                    provider=conn.provider,
                    name=getattr(conn, "name", f"{conn.provider.upper()} Connection"),
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "provider": conn.provider,
                        "name": getattr(
                            conn, "name", f"{conn.provider.upper()} Connection"
                        ),
                    },
                )
            )
            await db.execute(stmt)
        # Removed redundant commit here as JobProcessor handles it (BE-TRANS-1)

        # 2. Process each connection via its appropriate adapter
        checkpoint = job.payload.get("checkpoint", {}) if job.payload else {}
        completed_conns = checkpoint.get("completed_connections", [])

        for conn in connections:
            conn_id_str = str(conn.id)
            if conn_id_str in completed_conns:
                logger.info(
                    "skipping_already_ingested_connection", connection_id=conn_id_str
                )
                continue

            try:
                adapter = AdapterFactory.get_adapter(conn)

                # Stream costs using normalized interface
                cost_stream_or_awaitable = adapter.stream_cost_and_usage(
                    start_date=start_date, end_date=end_date, granularity="HOURLY"
                )
                cost_stream = await maybe_await(cost_stream_or_awaitable)

                records_ingested = 0
                total_cost_acc = 0.0

                async def tracking_wrapper(
                    stream: AsyncIterator[dict[str, Any]],
                ) -> AsyncGenerator[dict[str, Any], None]:
                    nonlocal records_ingested, total_cost_acc
                    provider_key = (
                        str(getattr(conn, "provider", "") or "").strip().lower()
                    )
                    async for raw in stream:
                        if not isinstance(raw, dict):
                            continue
                        r = dict(raw)
                        # Enforce a stable normalized ingestion shape. Adapters may omit optional
                        # fields; we fill defaults here so persistence is consistent across providers.
                        if provider_key:
                            r.setdefault("provider", provider_key)
                        r.setdefault("service", "Unknown")
                        r.setdefault("region", "global")
                        r.setdefault("usage_type", "Usage")
                        r.setdefault("currency", "USD")
                        r.setdefault("resource_id", None)
                        r.setdefault("usage_amount", None)
                        r.setdefault("usage_unit", None)
                        r.setdefault(
                            "source_adapter",
                            f"{r.get('provider') or provider_key or 'unknown'}_adapter",
                        )
                        if not isinstance(r.get("tags"), dict):
                            r["tags"] = {}
                        ts = r.get("timestamp")
                        if isinstance(ts, datetime) and ts.tzinfo is None:
                            r["timestamp"] = ts.replace(tzinfo=timezone.utc)

                        records_ingested += 1
                        total_cost_acc += float(r.get("cost_usd", 0) or 0)
                        yield r

                save_result = await persistence.save_records_stream(
                    records=tracking_wrapper(cost_stream),
                    tenant_id=str(tenant_id),
                    account_id=conn.id,  # Use UUID object (BE-UUID-1)
                    reconciliation_run_id=job.id,
                    is_preliminary=True,
                )

                conn.last_ingested_at = datetime.now(timezone.utc)
                db.add(conn)

                results.append(
                    {
                        "connection_id": str(conn.id),
                        "provider": conn.provider,
                        "records_ingested": save_result.get("records_saved", 0),
                        "total_cost": total_cost_acc,
                    }
                )
                total_records_ingested += int(save_result.get("records_saved", 0) or 0)

            except Exception as e:
                logger.error(
                    "cost_ingestion_connection_failed",
                    connection_id=str(conn.id),
                    error=str(e),
                )
                if hasattr(conn, "error_message"):
                    conn.error_message = str(e)[:255]
                    db.add(conn)
                results.append(
                    {
                        "connection_id": str(conn.id),
                        "status": "failed",
                        "error": str(e),
                        "total_cost": 0.0,
                    }
                )

            if conn_id_str not in completed_conns:
                completed_conns.append(conn_id_str)
                job.payload = {**checkpoint, "completed_connections": completed_conns}
                # Redundant commit removed (BE-TRANS-1)

        # 3. Trigger Attribution Engine (FinOps Audit 2)
        try:
            from app.modules.reporting.domain.attribution_engine import (
                AttributionEngine,
            )

            engine = AttributionEngine(db)
            if custom_window:
                attr_start = start_date.date()
                attr_end = end_date.date()
            else:
                # Use last 30 days for non-backfill ingestion.
                attr_end = datetime.now(timezone.utc).date()
                attr_start = attr_end - timedelta(days=30)
            await engine.apply_rules_to_tenant(
                tenant_id, start_date=attr_start, end_date=attr_end
            )
            logger.info("attribution_applied_post_ingestion", tenant_id=str(tenant_id))
        except Exception as e:
            logger.error(
                "attribution_trigger_failed", tenant_id=str(tenant_id), error=str(e)
            )

        return {
            "status": "completed",
            "connections_processed": len(connections),
            "ingested": total_records_ingested,
            "details": results,
            "window": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat(),
                "backfill": custom_window,
            },
        }


class CostForecastHandler(BaseJobHandler):
    """Handle multi-tenant cost forecasting as a background job."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator
        from app.shared.analysis.forecaster import SymbolicForecaster

        payload = job.payload or {}
        tenant_id = _require_tenant_id(job)
        start_date = _require_iso_date(payload, "start_date")
        end_date = _require_iso_date(payload, "end_date")
        days = payload.get("days", 30)
        provider = payload.get("provider")

        # 1. Fetch full summary for forecasting
        summary = await CostAggregator.get_summary(
            db, tenant_id, start_date, end_date, provider
        )

        if not summary.records:
            return {"status": "skipped", "reason": "no_data"}

        # 2. Run deterministic forecast
        # Phase 3: Symbolic Forecast
        result = await SymbolicForecaster.forecast(
            summary.records, days=days, db=db, tenant_id=tenant_id
        )

        return {"status": "completed", "forecast": result, "tenant_id": str(tenant_id)}


class CostAnomalyDetectionHandler(BaseJobHandler):
    """Deterministic daily cost anomaly detection with optional alert dispatch."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.anomaly_detection import (
            CostAnomalyDetectionService,
            dispatch_cost_anomaly_alerts,
        )
        from app.shared.core.pricing import (
            FeatureFlag,
            get_tenant_tier,
            is_feature_enabled,
        )

        tenant_id = _require_tenant_id(job)
        payload = job.payload or {}

        tier = await get_tenant_tier(tenant_id, db)
        if not is_feature_enabled(tier, FeatureFlag.ANOMALY_DETECTION):
            return {
                "status": "skipped",
                "reason": "feature_not_enabled_for_tier",
                "tier": tier.value,
            }

        target_date = (
            _require_iso_date(payload, "target_date")
            if payload.get("target_date")
            else datetime.now(timezone.utc).date()
        )
        lookback_days = int(payload.get("lookback_days", 28))
        min_abs_usd = Decimal(str(payload.get("min_abs_usd", "25")))
        min_percent = float(payload.get("min_percent", 30.0))
        min_severity = str(payload.get("min_severity", "medium")).strip().lower()
        provider = payload.get("provider")
        should_alert = bool(payload.get("alert", True)) and is_feature_enabled(
            tier, FeatureFlag.ALERTS
        )
        suppression_hours = int(payload.get("suppression_hours", 24))

        detector = CostAnomalyDetectionService(db)
        anomalies = await detector.detect(
            tenant_id=tenant_id,
            target_date=target_date,
            provider=provider,
            lookback_days=lookback_days,
            min_abs_usd=min_abs_usd,
            min_percent=min_percent,
            min_severity=min_severity,
        )

        alerted_count = 0
        if should_alert and anomalies:
            alerted_count = await dispatch_cost_anomaly_alerts(
                tenant_id=tenant_id,
                anomalies=anomalies,
                suppression_hours=suppression_hours,
                db=db,
            )

        return {
            "status": "completed",
            "tier": tier.value,
            "target_date": target_date.isoformat(),
            "lookback_days": lookback_days,
            "provider": provider,
            "count": len(anomalies),
            "alerted_count": alerted_count,
            "anomalies": [_serialize_anomaly(item) for item in anomalies[:50]],
        }


class CostExportHandler(BaseJobHandler):
    """Handle large cost data exports asynchronously."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator

        payload = job.payload or {}
        tenant_id = _require_tenant_id(job)
        start_date = _require_iso_date(payload, "start_date")
        end_date = _require_iso_date(payload, "end_date")
        export_format = payload.get("format", "json")

        logger.info(
            "cost_export_started",
            tenant_id=str(tenant_id),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        # 1. Get cached breakdown for fast aggregation
        breakdown = await CostAggregator.get_cached_breakdown(
            db, tenant_id, start_date, end_date
        )

        # 2. For detailed export, fetch full records
        summary = await CostAggregator.get_summary(db, tenant_id, start_date, end_date)

        # 3. Prepare export data
        export_data = {
            "tenant_id": str(tenant_id),
            "date_range": {"start": str(start_date), "end": str(end_date)},
            "summary": breakdown,
            "records_count": len(summary.records) if summary.records else 0,
            "total_cost": float(summary.total_cost) if summary.total_cost else 0,
        }

        logger.info(
            "cost_export_completed",
            tenant_id=str(tenant_id),
            records_exported=export_data["records_count"],
        )

        return {
            "status": "completed",
            "export_format": export_format,
            "records_exported": export_data["records_count"],
            "total_cost_usd": export_data["total_cost"],
            "download_url": None,  # In production: S3 presigned URL
        }


class CostAggregationHandler(BaseJobHandler):
    """Handle large cost data aggregations asynchronously."""

    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator

        payload = job.payload or {}
        tenant_id = _require_tenant_id(job)
        start_date = _require_iso_date(payload, "start_date")
        end_date = _require_iso_date(payload, "end_date")
        provider = payload.get("provider")

        logger.info(
            "cost_aggregation_job_started",
            tenant_id=str(tenant_id),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        # 1. Run the intensive aggregation (which is now protected by timeout/limits)
        # In a background job, we might relax the timeout slightly if needed,
        # but here we follow the same production rules.
        result = await CostAggregator.get_summary(
            db, tenant_id, start_date, end_date, provider
        )

        # 2. Store the result in the job's result field (serialized)
        # Note: Summary includes a list of potentially many records.
        # For very large results, we'd normally store in S3/Redis.
        # But for this implementation, we store a summary.

        return {
            "status": "completed",
            "total_cost_usd": float(result.total_cost),
            "record_count": len(result.records),
            "by_service": {k: float(v) for k, v in result.by_service.items()},
        }
