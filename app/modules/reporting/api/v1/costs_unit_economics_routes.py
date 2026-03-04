from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.api.v1.costs_models import (
    UnitEconomicsResponse,
    UnitEconomicsSettingsResponse,
    UnitEconomicsSettingsUpdate,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.notifications import NotificationDispatcher

logger = structlog.get_logger()


async def get_unit_economics_settings_impl(
    *,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    get_or_create_unit_settings: Callable[..., Awaitable[Any]],
    settings_to_response: Callable[[Any], UnitEconomicsSettingsResponse],
) -> UnitEconomicsSettingsResponse:
    tenant_id = require_tenant_id(user)
    settings = await get_or_create_unit_settings(db, tenant_id)
    return settings_to_response(settings)


async def update_unit_economics_settings_impl(
    *,
    payload: UnitEconomicsSettingsUpdate,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    get_or_create_unit_settings: Callable[..., Awaitable[Any]],
    settings_to_response: Callable[[Any], UnitEconomicsSettingsResponse],
) -> UnitEconomicsSettingsResponse:
    tenant_id = require_tenant_id(user)
    settings = await get_or_create_unit_settings(db, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings, key, value)
    await db.commit()
    await db.refresh(settings)
    return settings_to_response(settings)


async def get_unit_economics_impl(
    *,
    start_date: date,
    end_date: date,
    provider: str | None,
    request_volume: float | None,
    workload_volume: float | None,
    customer_volume: float | None,
    alert_on_anomaly: bool,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    get_or_create_unit_settings: Callable[..., Awaitable[Any]],
    window_total_cost: Callable[..., Awaitable[Any]],
    build_unit_metrics: Callable[..., Any],
) -> UnitEconomicsResponse:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = require_tenant_id(user)
    settings = await get_or_create_unit_settings(db, tenant_id)

    total_cost = await window_total_cost(db, tenant_id, start_date, end_date, provider)
    window_days = (end_date - start_date).days + 1
    baseline_end = start_date - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=window_days - 1)
    baseline_total_cost = await window_total_cost(
        db, tenant_id, baseline_start, baseline_end, provider
    )

    req_volume = float(request_volume or settings.default_request_volume)
    wkl_volume = float(workload_volume or settings.default_workload_volume)
    cst_volume = float(customer_volume or settings.default_customer_volume)
    threshold = float(settings.anomaly_threshold_percent)

    metrics = build_unit_metrics(
        total_cost=total_cost,
        baseline_total_cost=baseline_total_cost,
        threshold_percent=threshold,
        request_volume=req_volume,
        workload_volume=wkl_volume,
        customer_volume=cst_volume,
    )
    anomalies = [metric for metric in metrics if metric.is_anomalous]

    alert_dispatched = False
    if anomalies and alert_on_anomaly:
        try:
            top = anomalies[0]
            await NotificationDispatcher.send_alert(
                title="Unit Economics Anomaly Detected",
                message=(
                    f"Tenant {tenant_id}: {top.label} increased by {top.delta_percent:.2f}% "
                    f"from baseline for {start_date.isoformat()} to {end_date.isoformat()}."
                ),
                severity="warning",
                tenant_id=str(tenant_id),
                db=db,
            )
            alert_dispatched = True
        except (SQLAlchemyError, RuntimeError, ValueError, TypeError, OSError) as exc:
            logger.error(
                "unit_economics_alert_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                tenant_id=str(tenant_id),
            )

    return UnitEconomicsResponse(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_cost=float(total_cost),
        baseline_total_cost=float(baseline_total_cost),
        threshold_percent=threshold,
        anomaly_count=len(anomalies),
        alert_dispatched=alert_dispatched,
        metrics=metrics,
    )
