from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import structlog
from fastapi import HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.domain.aggregator import LARGE_DATASET_THRESHOLD
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import (
    FeatureFlag,
    is_feature_enabled,
)

logger = structlog.get_logger()


async def get_costs_impl(
    *,
    response: Response,
    start_date: date,
    end_date: date,
    provider: Optional[str],
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
    cost_aggregator_cls: Any,
) -> Any:
    tenant_id = require_tenant_id(current_user)
    record_count = await cost_aggregator_cls.count_records(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )

    if record_count > LARGE_DATASET_THRESHOLD:
        from app.models.background_job import JobType
        from app.modules.governance.domain.jobs.processor import enqueue_job

        job = await enqueue_job(
            db=db,
            tenant_id=tenant_id,
            job_type=JobType.COST_AGGREGATION,
            payload={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "provider": provider,
            },
        )
        response.status_code = 202
        return {
            "status": "accepted",
            "job_id": str(job.id),
            "record_count": record_count,
            "threshold": LARGE_DATASET_THRESHOLD,
        }

    return await cost_aggregator_cls.get_dashboard_summary(
        db,
        tenant_id,
        start_date,
        end_date,
        provider,
    )


async def get_cost_breakdown_impl(
    *,
    start_date: date,
    end_date: date,
    provider: Optional[str],
    limit: int,
    offset: int,
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
    cost_aggregator_cls: Any,
) -> Any:
    tenant_id = require_tenant_id(current_user)
    return await cost_aggregator_cls.get_basic_breakdown(
        db,
        tenant_id,
        start_date,
        end_date,
        provider,
        limit=limit,
        offset=offset,
    )


async def get_cost_attribution_summary_impl(
    *,
    start_date: date,
    end_date: date,
    bucket: Optional[str],
    limit: int,
    offset: int,
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
) -> dict[str, Any]:
    from app.modules.reporting.domain.attribution_engine import AttributionEngine

    tenant_id = require_tenant_id(current_user)
    attribution_engine = AttributionEngine(db)
    return await attribution_engine.get_allocation_summary(
        tenant_id=tenant_id,
        start_date=datetime.combine(start_date, time.min, tzinfo=timezone.utc),
        end_date=datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        bucket=bucket,
        limit=limit,
        offset=offset,
    )


async def get_cost_attribution_coverage_impl(
    *,
    start_date: date,
    end_date: date,
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
) -> dict[str, Any]:
    from app.modules.reporting.domain.attribution_engine import AttributionEngine

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    tenant_id = require_tenant_id(current_user)
    attribution_engine = AttributionEngine(db)
    return await attribution_engine.get_allocation_coverage(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        target_percentage=90.0,
    )


async def get_canonical_quality_impl(
    *,
    start_date: date,
    end_date: date,
    provider: Optional[str],
    notify_on_breach: bool,
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
    normalize_provider_filter: Any,
    cost_aggregator_cls: Any,
    notification_dispatcher_cls: Any,
) -> Any:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    tenant_id = require_tenant_id(current_user)
    normalized_provider = normalize_provider_filter(provider)
    quality = await cost_aggregator_cls.get_canonical_data_quality(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        provider=normalized_provider,
    )

    if (
        notify_on_breach
        and quality.get("total_records", 0) > 0
        and not quality.get("meets_target", False)
    ):
        try:
            await notification_dispatcher_cls.send_alert(
                title=(
                    "Canonical mapping coverage below target "
                    f"({quality.get('mapped_percentage', 0)}%)"
                ),
                message=(
                    f"Tenant {tenant_id} canonical mapping coverage is "
                    f"{quality.get('mapped_percentage', 0)}% vs target "
                    f"{quality.get('target_percentage', 99.0)}%. "
                    f"Unmapped records: {quality.get('unmapped_records', 0)}."
                ),
                severity="warning",
                tenant_id=str(tenant_id),
                db=db,
            )
            quality["alert_triggered"] = True
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError, OSError) as exc:
            logger.error(
                "canonical_quality_alert_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                tenant_id=str(tenant_id),
            )
            quality["alert_triggered"] = False
            quality["alert_error"] = str(exc)
            quality["alert_error_type"] = type(exc).__name__
    return quality


async def get_cost_forecast_impl(
    *,
    days: int,
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
    cost_aggregator_cls: Any,
    symbolic_forecaster_cls: Any,
) -> Any:
    tenant_id = require_tenant_id(current_user)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    summary = await cost_aggregator_cls.get_summary(db, tenant_id, start_date, end_date)

    if not summary.records:
        raise HTTPException(
            status_code=400,
            detail="Insufficient cost history for forecasting.",
        )

    return await symbolic_forecaster_cls.forecast(
        summary.records,
        days=days,
        db=db,
        tenant_id=tenant_id,
    )


async def get_cost_anomalies_impl(
    *,
    target_date: date,
    lookback_days: int,
    provider: Optional[str],
    min_abs_usd: float,
    min_percent: float,
    min_severity: str,
    alert: bool,
    suppression_hours: int,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Any,
    normalize_provider_filter: Any,
    validate_anomaly_severity: Any,
    anomaly_to_response_item: Any,
    anomaly_detection_service_cls: Any,
    dispatch_cost_anomaly_alerts_fn: Any,
) -> dict[str, Any]:
    tenant_id = require_tenant_id(user)
    normalized_provider = normalize_provider_filter(provider)
    normalized_severity = validate_anomaly_severity(min_severity)

    service = anomaly_detection_service_cls(db)
    anomalies = await service.detect(
        tenant_id=tenant_id,
        target_date=target_date,
        provider=normalized_provider,
        lookback_days=lookback_days,
        min_abs_usd=Decimal(str(min_abs_usd)),
        min_percent=min_percent,
        min_severity=normalized_severity,
    )

    alerted_count = 0
    if alert and anomalies:
        alerted_count = await dispatch_cost_anomaly_alerts_fn(
            tenant_id=tenant_id,
            anomalies=anomalies,
            suppression_hours=suppression_hours,
            db=db,
        )

    return {
        "target_date": target_date.isoformat(),
        "lookback_days": lookback_days,
        "provider": normalized_provider,
        "min_abs_usd": min_abs_usd,
        "min_percent": min_percent,
        "min_severity": normalized_severity,
        "count": len(anomalies),
        "alerted_count": alerted_count,
        "anomalies": [anomaly_to_response_item(item) for item in anomalies],
    }


async def analyze_costs_impl(
    *,
    request: Request,
    start_date: date,
    end_date: date,
    provider: Optional[str],
    db: AsyncSession,
    current_user: CurrentUser,
    require_tenant_id: Any,
    cost_aggregator_cls: Any,
    llm_factory_cls: Any,
    finops_analyzer_cls: Any,
) -> Any:
    tenant_id = require_tenant_id(current_user)
    summary = await cost_aggregator_cls.get_summary(
        db,
        tenant_id,
        start_date,
        end_date,
        provider,
    )

    if not summary.records:
        return {
            "summary": "No cost data available for analysis.",
            "anomalies": [],
            "recommendations": [],
            "estimated_total_savings": 0.0,
        }

    llm = llm_factory_cls.create()
    analyzer = finops_analyzer_cls(llm, db)
    return await analyzer.analyze(
        usage_summary=summary,
        tenant_id=tenant_id,
        db=db,
        provider=provider,
        user_id=current_user.id,
        client_ip=request.client.host if request.client else None,
    )


async def trigger_ingest_impl(
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    db: AsyncSession,
    current_user: CurrentUser,
    resolve_user_tier: Any,
    require_tenant_id: Any,
) -> dict[str, str]:
    if (start_date is None) ^ (end_date is None):
        raise HTTPException(
            status_code=400,
            detail="Both start_date and end_date are required for backfill",
        )
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    if start_date is not None and end_date is not None:
        user_tier = resolve_user_tier(current_user)
        if not is_feature_enabled(user_tier, FeatureFlag.INGESTION_BACKFILL):
            raise HTTPException(
                status_code=403,
                detail=(
                    "Historical backfill requires Growth tier or higher. "
                    "Please upgrade."
                ),
            )

    from app.models.background_job import JobType
    from app.modules.governance.domain.jobs.processor import enqueue_job

    tenant_id = require_tenant_id(current_user)
    payload: dict[str, Any] = {}
    if start_date is not None and end_date is not None:
        payload = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

    job = await enqueue_job(
        db=db,
        tenant_id=tenant_id,
        job_type=JobType.COST_INGESTION,
        payload=payload,
    )
    response: dict[str, str] = {"status": "queued", "job_id": str(job.id)}
    if payload:
        response["start_date"] = payload["start_date"]
        response["end_date"] = payload["end_date"]
    return response


async def get_ingestion_sla_impl(
    *,
    window_hours: int,
    target_success_rate_percent: float,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Any,
    compute_ingestion_sla_metrics: Any,
) -> Any:
    tenant_id = require_tenant_id(user)
    return await compute_ingestion_sla_metrics(
        db=db,
        tenant_id=tenant_id,
        window_hours=window_hours,
        target_success_rate_percent=target_success_rate_percent,
    )
