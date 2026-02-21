from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.cloud import CloudAccount, CostRecord
from app.models.license_connection import LicenseConnection
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.models.unit_economics_settings import UnitEconomicsSettings
from app.shared.core.connection_state import is_connection_active

from .costs_models import (
    AcceptanceKpiMetric,
    IngestionSLAResponse,
    ProviderRecencyResponse,
    UnitEconomicsSettingsResponse,
)


def settings_to_response(
    settings: UnitEconomicsSettings,
) -> UnitEconomicsSettingsResponse:
    return UnitEconomicsSettingsResponse(
        id=settings.id,
        default_request_volume=float(settings.default_request_volume),
        default_workload_volume=float(settings.default_workload_volume),
        default_customer_volume=float(settings.default_customer_volume),
        anomaly_threshold_percent=float(settings.anomaly_threshold_percent),
    )


async def get_or_create_unit_settings(
    db: AsyncSession, tenant_id: UUID
) -> UnitEconomicsSettings:
    settings = await db.scalar(
        select(UnitEconomicsSettings).where(
            UnitEconomicsSettings.tenant_id == tenant_id
        )
    )
    if settings:
        return settings

    settings = UnitEconomicsSettings(tenant_id=tenant_id)
    db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings


async def window_total_cost(
    db: AsyncSession,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
    provider: Optional[str] = None,
) -> Decimal:
    stmt = select(func.coalesce(func.sum(CostRecord.cost_usd), 0)).where(
        CostRecord.tenant_id == tenant_id,
        CostRecord.recorded_at >= start_date,
        CostRecord.recorded_at <= end_date,
    )
    if provider:
        stmt = stmt.join(CloudAccount, CostRecord.account_id == CloudAccount.id).where(
            CloudAccount.provider == provider.lower()
        )
    result = await db.execute(stmt)
    value = result.scalar_one_or_none()
    if value is None:
        return Decimal("0")
    return Decimal(value)


def is_connection_active_state(connection: Any) -> bool:
    return is_connection_active(connection)


def build_provider_recency_summary(
    provider: str,
    connections: list[Any],
    *,
    now: datetime,
    recency_target_hours: int,
) -> ProviderRecencyResponse:
    threshold = now - timedelta(hours=recency_target_hours)
    active_connections = [conn for conn in connections if is_connection_active_state(conn)]

    recently_ingested = 0
    stale_connections = 0
    never_ingested = 0
    latest_ingested_at: Optional[datetime] = None

    for conn in active_connections:
        last_ingested_at = getattr(conn, "last_ingested_at", None)
        if isinstance(last_ingested_at, datetime):
            if last_ingested_at.tzinfo is None:
                last_ingested_at = last_ingested_at.replace(tzinfo=timezone.utc)
            if latest_ingested_at is None or last_ingested_at > latest_ingested_at:
                latest_ingested_at = last_ingested_at
            if last_ingested_at >= threshold:
                recently_ingested += 1
            else:
                stale_connections += 1
        else:
            never_ingested += 1

    meets_recency_target = (
        len(active_connections) > 0 and stale_connections == 0 and never_ingested == 0
    )

    return ProviderRecencyResponse(
        provider=provider,
        active_connections=len(active_connections),
        recently_ingested=recently_ingested,
        stale_connections=stale_connections,
        never_ingested=never_ingested,
        latest_ingested_at=latest_ingested_at.isoformat() if latest_ingested_at else None,
        recency_target_hours=recency_target_hours,
        meets_recency_target=meets_recency_target,
    )


async def compute_provider_recency_summaries(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    recency_target_hours: int,
) -> list[ProviderRecencyResponse]:
    from app.models.aws_connection import AWSConnection
    from app.models.azure_connection import AzureConnection
    from app.models.gcp_connection import GCPConnection
    from app.models.hybrid_connection import HybridConnection
    from app.models.platform_connection import PlatformConnection
    from app.models.saas_connection import SaaSConnection

    now = datetime.now(timezone.utc)
    provider_models: list[tuple[str, Any]] = [
        ("aws", AWSConnection),
        ("azure", AzureConnection),
        ("gcp", GCPConnection),
        ("saas", SaaSConnection),
        ("license", LicenseConnection),
        ("platform", PlatformConnection),
        ("hybrid", HybridConnection),
    ]
    summaries: list[ProviderRecencyResponse] = []
    for provider, model in provider_models:
        result = await db.execute(select(model).where(model.tenant_id == tenant_id))
        connections = list(result.scalars().all())
        summaries.append(
            build_provider_recency_summary(
                provider,
                connections,
                now=now,
                recency_target_hours=recency_target_hours,
            )
        )
    return summaries


async def compute_ingestion_sla_metrics(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    window_hours: int,
    target_success_rate_percent: float,
) -> IngestionSLAResponse:
    window_start = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    result = await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == tenant_id,
            BackgroundJob.job_type == JobType.COST_INGESTION.value,
            BackgroundJob.created_at >= window_start,
        )
    )
    jobs = list(result.scalars().all())

    total_jobs = len(jobs)
    successful_jobs = sum(1 for job in jobs if job.status == JobStatus.COMPLETED.value)
    failed_jobs = sum(
        1
        for job in jobs
        if job.status in {JobStatus.FAILED.value, JobStatus.DEAD_LETTER.value}
    )
    success_rate_percent = (
        round((successful_jobs / total_jobs) * 100, 2) if total_jobs else 0.0
    )
    meets_sla = total_jobs > 0 and success_rate_percent >= target_success_rate_percent

    latest_completed_at_dt: Optional[datetime] = None
    duration_samples: list[float] = []
    records_ingested = 0

    for job in jobs:
        if job.completed_at and (
            latest_completed_at_dt is None or job.completed_at > latest_completed_at_dt
        ):
            latest_completed_at_dt = job.completed_at

        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            if duration >= 0:
                duration_samples.append(duration)

        if job.status == JobStatus.COMPLETED.value and isinstance(job.result, dict):
            ingested_value = job.result.get("ingested")
            if isinstance(ingested_value, (int, float)):
                records_ingested += int(ingested_value)

    avg_duration_seconds = (
        round(sum(duration_samples) / len(duration_samples), 2)
        if duration_samples
        else None
    )
    p95_duration_seconds: Optional[float] = None
    if duration_samples:
        sorted_durations = sorted(duration_samples)
        p95_index = max(0, math.ceil(len(sorted_durations) * 0.95) - 1)
        p95_duration_seconds = round(sorted_durations[p95_index], 2)

    return IngestionSLAResponse(
        window_hours=window_hours,
        target_success_rate_percent=round(target_success_rate_percent, 2),
        total_jobs=total_jobs,
        successful_jobs=successful_jobs,
        failed_jobs=failed_jobs,
        success_rate_percent=success_rate_percent,
        meets_sla=meets_sla,
        latest_completed_at=latest_completed_at_dt.isoformat()
        if latest_completed_at_dt
        else None,
        avg_duration_seconds=avg_duration_seconds,
        p95_duration_seconds=p95_duration_seconds,
        records_ingested=records_ingested,
    )


async def compute_license_governance_kpi(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
) -> AcceptanceKpiMetric:
    """Compute deterministic license-governance reliability KPI for acceptance evidence."""
    active_connections = int(
        await db.scalar(
            select(func.count(LicenseConnection.id)).where(
                LicenseConnection.tenant_id == tenant_id,
                LicenseConnection.is_active,
            )
        )
        or 0
    )

    if active_connections <= 0:
        return AcceptanceKpiMetric(
            key="license_governance_reliability",
            label="License Governance Reliability",
            available=False,
            target="At least one active license connection",
            actual="No active license connections",
            meets_target=False,
            details={
                "active_license_connections": 0,
                "total_requests": 0,
                "completed_requests": 0,
                "failed_requests": 0,
                "in_flight_requests": 0,
            },
        )

    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), time.min).replace(
        tzinfo=timezone.utc
    )
    in_flight_statuses = (
        RemediationStatus.PENDING,
        RemediationStatus.PENDING_APPROVAL,
        RemediationStatus.APPROVED,
        RemediationStatus.SCHEDULED,
        RemediationStatus.EXECUTING,
    )

    counts_stmt = select(
        func.count(RemediationRequest.id).label("total_requests"),
        func.count(RemediationRequest.id)
        .filter(RemediationRequest.status == RemediationStatus.COMPLETED)
        .label("completed_requests"),
        func.count(RemediationRequest.id)
        .filter(RemediationRequest.status == RemediationStatus.FAILED)
        .label("failed_requests"),
        func.count(RemediationRequest.id)
        .filter(RemediationRequest.status.in_(in_flight_statuses))
        .label("in_flight_requests"),
    ).where(
        RemediationRequest.tenant_id == tenant_id,
        RemediationRequest.action == RemediationAction.RECLAIM_LICENSE_SEAT,
        RemediationRequest.created_at >= start_dt,
        RemediationRequest.created_at < end_dt_exclusive,
    )
    counts_row = (await db.execute(counts_stmt)).one()

    total_requests = int(getattr(counts_row, "total_requests", 0) or 0)
    completed_requests = int(getattr(counts_row, "completed_requests", 0) or 0)
    failed_requests = int(getattr(counts_row, "failed_requests", 0) or 0)
    in_flight_requests = int(getattr(counts_row, "in_flight_requests", 0) or 0)

    completion_rate = (
        round((completed_requests / total_requests) * 100.0, 2)
        if total_requests > 0
        else 100.0
    )
    failure_rate = (
        round((failed_requests / total_requests) * 100.0, 2)
        if total_requests > 0
        else 0.0
    )
    in_flight_ratio = (
        round((in_flight_requests / total_requests) * 100.0, 2)
        if total_requests > 0
        else 0.0
    )

    completed_rows = (
        await db.execute(
            select(RemediationRequest.created_at, RemediationRequest.executed_at).where(
                RemediationRequest.tenant_id == tenant_id,
                RemediationRequest.action == RemediationAction.RECLAIM_LICENSE_SEAT,
                RemediationRequest.status == RemediationStatus.COMPLETED,
                RemediationRequest.created_at >= start_dt,
                RemediationRequest.created_at < end_dt_exclusive,
                RemediationRequest.executed_at.is_not(None),
            )
        )
    ).all()
    cycle_hours: list[float] = []
    for created_at, executed_at in completed_rows:
        if created_at is None or executed_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)
        if executed_at >= created_at:
            cycle_hours.append((executed_at - created_at).total_seconds() / 3600.0)

    avg_time_to_complete_hours = (
        round(sum(cycle_hours) / len(cycle_hours), 2) if cycle_hours else None
    )

    completion_target = 70.0
    failure_target = 20.0
    in_flight_target = 50.0
    meets_target = (
        completion_rate >= completion_target
        and failure_rate <= failure_target
        and in_flight_ratio <= in_flight_target
    )

    return AcceptanceKpiMetric(
        key="license_governance_reliability",
        label="License Governance Reliability",
        available=True,
        target=(
            f">={completion_target:.0f}% completion, "
            f"<={failure_target:.0f}% failures, <= {in_flight_target:.0f}% in-flight"
        ),
        actual=(
            f"{completion_rate:.2f}% completion, {failure_rate:.2f}% failed, "
            f"{in_flight_requests}/{total_requests} in-flight"
        ),
        meets_target=meets_target,
        details={
            "active_license_connections": active_connections,
            "total_requests": total_requests,
            "completed_requests": completed_requests,
            "failed_requests": failed_requests,
            "in_flight_requests": in_flight_requests,
            "completion_rate_percent": completion_rate,
            "failure_rate_percent": failure_rate,
            "in_flight_ratio_percent": in_flight_ratio,
            "avg_time_to_complete_hours": avg_time_to_complete_hours,
            "window": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        },
    )
