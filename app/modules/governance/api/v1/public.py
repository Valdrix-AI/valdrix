from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.sso_domain_mapping import SsoDomainMapping
from app.shared.core.pricing import FeatureFlag, is_feature_enabled, normalize_tier
from app.shared.lead_gen.assessment import FreeAssessmentService
from app.shared.core.rate_limit import auth_limit, rate_limit
from app.shared.core.turnstile import (
    require_turnstile_for_public_assessment,
    require_turnstile_for_sso_discovery,
)
from app.shared.core.ops_metrics import (
    LANDING_TELEMETRY_EVENTS_TOTAL,
    LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL,
)
from app.shared.db.session import get_system_db

router = APIRouter()
assessment_service = FreeAssessmentService()
logger = structlog.get_logger()
_LANDING_LABEL_SANITIZER = re.compile(r"[^a-z0-9_]+")
_LANDING_MAX_AGE = timedelta(days=2)
_LANDING_MAX_FUTURE_SKEW = timedelta(minutes=5)


def _normalize_email_domain(email: str) -> str:
    value = str(email or "").strip().lower()
    if "@" not in value:
        return ""
    domain = value.split("@", 1)[1].strip().lower().strip(".")
    return domain


class SsoDiscoveryRequest(BaseModel):
    email: EmailStr = Field(
        ..., description="User email used to locate tenant SSO federation config."
    )


class SsoDiscoveryResponse(BaseModel):
    available: bool
    mode: Literal["domain", "provider_id"] | None = None
    domain: str | None = None
    provider_id: str | None = None
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


class LandingTelemetryExperiment(BaseModel):
    hero: str | None = Field(default=None, max_length=96)
    cta: str | None = Field(default=None, max_length=96)
    order: str | None = Field(default=None, max_length=96)

    model_config = ConfigDict(extra="forbid")


class LandingTelemetryUtm(BaseModel):
    source: str | None = Field(default=None, max_length=96)
    medium: str | None = Field(default=None, max_length=96)
    campaign: str | None = Field(default=None, max_length=96)
    term: str | None = Field(default=None, max_length=96)
    content: str | None = Field(default=None, max_length=96)

    model_config = ConfigDict(extra="forbid")


class LandingTelemetryRequest(BaseModel):
    event_id: str | None = Field(default=None, alias="eventId", max_length=64)
    name: str = Field(..., max_length=96)
    section: str = Field(..., max_length=96)
    value: str | None = Field(default=None, max_length=96)
    visitor_id: str | None = Field(default=None, alias="visitorId", max_length=96)
    persona: str | None = Field(default=None, max_length=64)
    funnel_stage: str | None = Field(default=None, alias="funnelStage", max_length=64)
    page_path: str | None = Field(default=None, alias="pagePath", max_length=256)
    referrer: str | None = Field(default=None, max_length=256)
    experiment: LandingTelemetryExperiment | None = None
    utm: LandingTelemetryUtm | None = None
    timestamp: datetime

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LandingTelemetryResponse(BaseModel):
    status: Literal["accepted", "ignored"]
    ingest_id: str | None = None
    reason: str | None = None

    model_config = ConfigDict(extra="forbid")


def _normalize_landing_label(raw: str | None, fallback: str) -> str:
    token = (raw or "").strip().lower()
    if not token:
        return fallback
    token = _LANDING_LABEL_SANITIZER.sub("_", token).strip("_")
    if not token:
        return fallback
    return token[:64]


def _normalize_event_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/csrf")
@auth_limit
async def get_csrf_token(request: Request) -> JSONResponse:
    """
    Get a CSRF token to be used in subsequent POST/PUT/DELETE requests.
    Sets the fast-csrf-token cookie and returns the token in the body.
    """
    from fastapi_csrf_protect import CsrfProtect

    csrf = CsrfProtect()

    token, signed_token = csrf.generate_csrf_tokens()
    response = JSONResponse(content={"csrf_token": token})
    csrf.set_csrf_cookie(signed_token, response)
    return response


@router.post("/assessment", response_model=None)
@rate_limit("5/day")
async def run_public_assessment(
    request: Request,
    body: Dict[str, Any],
    _turnstile: None = Depends(require_turnstile_for_public_assessment),
) -> Dict[str, Any] | JSONResponse:
    """
    Public endpoint for lead-gen cost assessment.
    Limited to 5 requests per day per IP to prevent abuse.
    """
    try:
        result = await assessment_service.run_assessment(body)
        return result
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "code": "VALUE_ERROR",
                "message": str(e),
            },
        )
    except Exception:
        # Don't leak internals for public endpoints
        raise HTTPException(
            status_code=500, detail="An unexpected error occurred during assessment"
        )


@router.post("/sso/discovery", response_model=SsoDiscoveryResponse)
@rate_limit("30/minute")
async def discover_sso_federation(
    request: Request,
    payload: SsoDiscoveryRequest,
    _turnstile: None = Depends(require_turnstile_for_sso_discovery),
    db: AsyncSession = Depends(get_system_db),
) -> SsoDiscoveryResponse:
    """
    Discover tenant-scoped SSO federation bootstrap configuration from email domain.

    This endpoint is intentionally public so login pages can resolve whether they should
    initiate an IdP federation flow (Supabase signInWithSSO).
    """
    del request  # rate limiter dependency consumes request context

    domain = _normalize_email_domain(payload.email)
    if not domain:
        return SsoDiscoveryResponse(available=False, reason="invalid_email_domain")

    stmt = (
        select(SsoDomainMapping, Tenant.plan)
        .join(Tenant, SsoDomainMapping.tenant_id == Tenant.id)
        .where(SsoDomainMapping.domain == domain)
        .where(SsoDomainMapping.is_active.is_(True))
    )
    try:
        rows = (await asyncio.wait_for(db.execute(stmt), timeout=10.0)).all()
    except TimeoutError:
        logger.warning("sso_discovery_backend_timeout", domain=domain)
        return SsoDiscoveryResponse(available=False, reason="sso_discovery_backend_timeout")
    except Exception:
        logger.exception("sso_discovery_backend_error", domain=domain)
        return SsoDiscoveryResponse(available=False, reason="sso_discovery_backend_error")
    if not rows:
        return SsoDiscoveryResponse(
            available=False, reason="sso_not_configured_for_domain"
        )
    if len(rows) > 1:
        # Defense-in-depth: the DB should prevent this via unique constraints.
        return SsoDiscoveryResponse(
            available=False, reason="ambiguous_tenant_domain_mapping"
        )

    mapping, raw_plan = rows[0]
    tier = normalize_tier(raw_plan)
    if not is_feature_enabled(tier, FeatureFlag.SSO):
        return SsoDiscoveryResponse(
            available=False, reason="tier_not_eligible_for_sso_federation"
        )

    mode = (
        str(getattr(mapping, "federation_mode", "domain") or "domain").strip().lower()
    )
    if mode not in {"domain", "provider_id"}:
        mode = "domain"

    if mode == "provider_id":
        provider_id = str(getattr(mapping, "provider_id", "") or "").strip()
        if not provider_id:
            return SsoDiscoveryResponse(
                available=False, reason="sso_provider_id_not_configured"
            )
        return SsoDiscoveryResponse(
            available=True,
            mode="provider_id",
            provider_id=provider_id,
        )

    return SsoDiscoveryResponse(
        available=True,
        mode="domain",
        domain=domain,
    )


@router.post("/landing/events", response_model=LandingTelemetryResponse, status_code=202)
@rate_limit("240/minute")
async def ingest_landing_event(
    request: Request,
    payload: LandingTelemetryRequest,
) -> LandingTelemetryResponse:
    now = datetime.now(timezone.utc)
    event_timestamp = _normalize_event_timestamp(payload.timestamp)
    if event_timestamp < now - _LANDING_MAX_AGE or event_timestamp > now + _LANDING_MAX_FUTURE_SKEW:
        LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL.labels(outcome="rejected_timestamp").inc()
        return LandingTelemetryResponse(
            status="ignored",
            reason="timestamp_out_of_bounds",
        )

    event_name = _normalize_landing_label(payload.name, "unknown_action")
    section = _normalize_landing_label(payload.section, "unknown_section")
    funnel_stage = _normalize_landing_label(payload.funnel_stage, "unknown_stage")
    persona = _normalize_landing_label(payload.persona, "unknown_persona")
    value = _normalize_landing_label(payload.value, "")
    visitor_prefix = (payload.visitor_id or "").strip()[:24]
    event_id = (payload.event_id or "").strip() or str(uuid.uuid4())
    client_ip = getattr(request.client, "host", "") or "unknown"
    client_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:12]

    LANDING_TELEMETRY_EVENTS_TOTAL.labels(
        event_name=event_name,
        section=section,
        funnel_stage=funnel_stage,
    ).inc()
    LANDING_TELEMETRY_INGEST_OUTCOMES_TOTAL.labels(outcome="accepted").inc()

    logger.info(
        "landing_telemetry_ingested",
        ingest_id=event_id,
        event_name=event_name,
        section=section,
        value=value or None,
        funnel_stage=funnel_stage,
        persona=persona,
        page_path=(payload.page_path or "")[:160] or None,
        visitor_prefix=visitor_prefix or None,
        client_hash=client_hash,
        source="web_landing",
    )
    return LandingTelemetryResponse(status="accepted", ingest_id=event_id)
