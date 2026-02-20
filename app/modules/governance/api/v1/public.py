from __future__ import annotations

import asyncio
from typing import Any, Dict, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.sso_domain_mapping import SsoDomainMapping
from app.shared.core.pricing import PricingTier, normalize_tier
from app.shared.lead_gen.assessment import FreeAssessmentService
from app.shared.core.rate_limit import auth_limit, rate_limit
from app.shared.db.session import get_system_db

router = APIRouter()
assessment_service = FreeAssessmentService()
logger = structlog.get_logger()


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
    request: Request, body: Dict[str, Any]
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
    if tier not in {PricingTier.PRO, PricingTier.ENTERPRISE}:
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
