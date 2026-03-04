"""
Acceptance capture runtime helpers and typed recoverable exception sets.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from httpx import HTTPError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob
from app.modules.governance.domain.security.audit_log import (
    AuditEventType,
    AuditLog,
)
from app.shared.core.pricing import PricingTier, normalize_tier

ACCEPTANCE_CAPTURE_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    SQLAlchemyError,
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)
ACCEPTANCE_INTEGRATION_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    SQLAlchemyError,
    HTTPError,
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)
ACCEPTANCE_PARSE_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    TypeError,
    ValueError,
)


def _require_tenant_id(job: BackgroundJob) -> UUID:
    if job.tenant_id is None:
        raise ValueError("tenant_id required for acceptance_suite_capture")
    return UUID(str(job.tenant_id))


def _iso_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("Expected ISO date string")


def _tenant_tier(plan: str | None) -> PricingTier:
    if not plan:
        return PricingTier.FREE
    return normalize_tier(plan)


def _coerce_positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


async def _evaluate_tenancy_passive_check(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    max_age_hours: int,
    now_utc: datetime,
) -> dict[str, Any]:
    latest = await db.scalar(
        select(AuditLog)
        .where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.event_type
            == AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value,
        )
        .order_by(AuditLog.event_timestamp.desc())
        .limit(1)
    )

    if latest is None:
        return {
            "success": False,
            "status_code": 503,
            "message": "Tenant isolation verification evidence is missing.",
            "details": {
                "max_age_hours": max_age_hours,
                "reason": "evidence_missing",
            },
        }

    observed = latest.event_timestamp
    if observed.tzinfo is None:
        observed_utc = observed.replace(tzinfo=timezone.utc)
    else:
        observed_utc = observed.astimezone(timezone.utc)
    age_hours = (now_utc - observed_utc).total_seconds() / 3600.0

    if not bool(getattr(latest, "success", False)):
        return {
            "success": False,
            "status_code": 503,
            "message": "Latest tenant isolation verification did not pass.",
            "details": {
                "max_age_hours": max_age_hours,
                "age_hours": round(age_hours, 4),
                "reason": "latest_verification_failed",
                "evidence_correlation_id": getattr(latest, "correlation_id", None),
            },
        }

    if age_hours > float(max_age_hours):
        return {
            "success": False,
            "status_code": 504,
            "message": "Tenant isolation verification evidence is stale.",
            "details": {
                "max_age_hours": max_age_hours,
                "age_hours": round(age_hours, 4),
                "reason": "evidence_stale",
                "evidence_correlation_id": getattr(latest, "correlation_id", None),
            },
        }

    return {
        "success": True,
        "status_code": 200,
        "message": "Tenant isolation passive check OK.",
        "details": {
            "max_age_hours": max_age_hours,
            "age_hours": round(age_hours, 4),
            "evidence_correlation_id": getattr(latest, "correlation_id", None),
        },
    }


def _integration_event_type(channel: str) -> AuditEventType:
    normalized = channel.strip().lower()
    if normalized == "slack":
        return AuditEventType.INTEGRATION_TEST_SLACK
    if normalized == "jira":
        return AuditEventType.INTEGRATION_TEST_JIRA
    if normalized == "teams":
        return AuditEventType.INTEGRATION_TEST_TEAMS
    if normalized == "workflow":
        return AuditEventType.INTEGRATION_TEST_WORKFLOW
    if normalized == "tenancy":
        return AuditEventType.INTEGRATION_TEST_TENANCY
    return AuditEventType.INTEGRATION_TEST_SUITE
