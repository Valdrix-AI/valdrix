"""
Tenant Identity Settings API

SSO:
- Enforced as allowed email-domain restrictions at the API layer.

SCIM (Enterprise):
- Tenant-scoped bearer token used to authenticate SCIM provisioning calls.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant_identity_settings import TenantIdentitySettings
from app.models.sso_domain_mapping import SsoDomainMapping
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    is_feature_enabled,
    normalize_tier,
)
from app.shared.core.config import get_settings
from app.shared.core.security import generate_secret_blind_index
from app.shared.db.session import get_db
from app.shared.core.approval_permissions import (
    SUPPORTED_APPROVAL_PERMISSIONS,
    normalize_approval_permissions,
)

logger = structlog.get_logger()
router = APIRouter(tags=["Identity"])

SCIM_TOKEN_ROTATION_RECOMMENDED_DAYS = 90
SUPPORTED_SCIM_MAPPING_ROLES = {"admin", "member"}
SUPPORTED_PERSONAS = {"engineering", "finance", "platform", "leadership"}
SUPPORTED_SSO_FEDERATION_MODES = {"domain", "provider_id"}
SUPPORTED_SCIM_APPROVAL_PERMISSIONS = tuple(sorted(SUPPORTED_APPROVAL_PERMISSIONS))


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except Exception:  # noqa: BLE001
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _normalize_domains(domains: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in domains:
        domain = str(value).strip().lower()
        if not domain:
            continue
        if "@" in domain:
            domain = domain.split("@")[-1].strip().lower()
        domain = domain.strip(".")
        if not domain:
            continue
        if domain not in normalized:
            normalized.append(domain)
    return normalized


def _generate_scim_token() -> str:
    # URL-safe and long enough to withstand brute force.
    return secrets.token_urlsafe(48)


class IdentitySettingsResponse(BaseModel):
    sso_enabled: bool
    allowed_email_domains: list[str]
    sso_federation_enabled: bool
    sso_federation_mode: str
    sso_federation_provider_id: str | None
    scim_enabled: bool
    has_scim_token: bool
    scim_last_rotated_at: str | None
    scim_group_mappings: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ScimGroupMapping(BaseModel):
    group: str = Field(
        ..., min_length=1, max_length=255, description="IdP group name/display name."
    )
    role: str = Field(
        ...,
        description="Valdrix role to assign when user is in the group: admin|member.",
    )
    persona: str | None = Field(
        default=None,
        description="Optional persona default for users in this group (engineering|finance|platform|leadership).",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Optional scoped approval permissions granted to users in this group. "
            f"Supported values: {', '.join(SUPPORTED_SCIM_APPROVAL_PERMISSIONS)}."
        ),
    )

    @field_validator("group")
    @classmethod
    def _validate_group(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("group must not be empty")
        return normalized.lower()

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in SUPPORTED_SCIM_MAPPING_ROLES:
            raise ValueError("role must be one of: admin, member")
        return normalized

    @field_validator("persona")
    @classmethod
    def _validate_persona(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        if normalized not in SUPPORTED_PERSONAS:
            raise ValueError(
                "persona must be one of: engineering, finance, platform, leadership"
            )
        return normalized

    @field_validator("permissions", mode="before")
    @classmethod
    def _validate_permissions(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("permissions must be a list of strings")

        normalized = normalize_approval_permissions(value)
        if len(normalized) != len(
            {str(item or "").strip().lower() for item in value if str(item or "").strip()}
        ):
            supported = ", ".join(SUPPORTED_SCIM_APPROVAL_PERMISSIONS)
            raise ValueError(f"permissions must only include: {supported}")
        return normalized


class IdentitySettingsUpdate(BaseModel):
    sso_enabled: bool = Field(
        False, description="Enable domain allowlisting enforcement for this tenant."
    )
    allowed_email_domains: list[str] = Field(
        default_factory=list,
        description="Allowed email domains (e.g. example.com). Only enforced when sso_enabled is true.",
        max_length=50,
    )
    sso_federation_enabled: bool = Field(
        False,
        description=(
            "Enable real IdP login federation (Supabase SSO bootstrap). "
            "When disabled, only post-login allowlist enforcement is active."
        ),
    )
    sso_federation_mode: str = Field(
        "domain",
        description="Federation bootstrap mode: domain | provider_id.",
    )
    sso_federation_provider_id: str | None = Field(
        default=None,
        max_length=255,
        description="Supabase SSO provider_id (required when sso_federation_mode=provider_id).",
    )
    scim_enabled: bool = Field(
        False, description="Enable SCIM provisioning (Enterprise feature)."
    )
    scim_group_mappings: list[ScimGroupMapping] = Field(
        default_factory=list,
        max_length=50,
        description="Optional IdP group mappings used by SCIM provisioning for role/persona assignment (Enterprise).",
    )

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def validate_domains(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return _normalize_domains([str(v) for v in value])
        raise ValueError("allowed_email_domains must be a list of domain strings")

    @model_validator(mode="after")
    def _validate_unique_scim_groups(self) -> "IdentitySettingsUpdate":
        seen: set[str] = set()
        for mapping in self.scim_group_mappings:
            if mapping.group in seen:
                raise ValueError(
                    f"Duplicate scim_group_mappings entry for group '{mapping.group}'."
                )
            seen.add(mapping.group)
        mode = str(self.sso_federation_mode or "").strip().lower()
        if mode not in SUPPORTED_SSO_FEDERATION_MODES:
            raise ValueError("sso_federation_mode must be one of: domain, provider_id")
        self.sso_federation_mode = mode

        provider_id = str(self.sso_federation_provider_id or "").strip() or None
        self.sso_federation_provider_id = provider_id

        if self.sso_federation_enabled:
            if not self.sso_enabled:
                raise ValueError(
                    "Enable sso_enabled before enabling sso_federation_enabled."
                )
            if mode == "provider_id" and not provider_id:
                raise ValueError(
                    "sso_federation_provider_id is required when sso_federation_mode=provider_id."
                )
        return self


class RotateScimTokenResponse(BaseModel):
    scim_token: str
    rotated_at: str


class SsoDiagnostics(BaseModel):
    enabled: bool
    allowed_email_domains: list[str]
    enforcement_active: bool
    federation_enabled: bool
    federation_mode: str
    federation_ready: bool
    current_admin_domain: str | None
    current_admin_domain_allowed: bool | None
    issues: list[str] = Field(default_factory=list)


class ScimDiagnostics(BaseModel):
    available: bool
    enabled: bool
    has_token: bool
    token_blind_index_present: bool
    last_rotated_at: str | None
    token_age_days: int | None
    rotation_recommended_days: int
    rotation_overdue: bool
    issues: list[str] = Field(default_factory=list)


class IdentityDiagnosticsResponse(BaseModel):
    tier: str
    sso: SsoDiagnostics
    scim: ScimDiagnostics
    recommendations: list[str] = Field(default_factory=list)


class SsoFederationValidationCheck(BaseModel):
    name: str
    passed: bool
    severity: str = Field(default="error", description="info|warning|error")
    detail: str | None = None


class SsoFederationValidationResponse(BaseModel):
    tier: str
    enforcement_active: bool
    federation_enabled: bool
    federation_mode: str
    provider_id_configured: bool
    frontend_url: str
    expected_redirect_url: str
    discovery_endpoint: str
    passed: bool
    checks: list[SsoFederationValidationCheck] = Field(default_factory=list)


class ScimTokenTestRequest(BaseModel):
    scim_token: str = Field(
        ...,
        min_length=10,
        description="The SCIM bearer token you configured in your IdP.",
    )


class ScimTokenTestResponse(BaseModel):
    status: str
    token_matches: bool


@router.get("/identity", response_model=IdentitySettingsResponse)
async def get_identity_settings(
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SSO, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> IdentitySettingsResponse:
    """
    Get (or create) identity settings for this tenant.
    """
    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = TenantIdentitySettings(
            tenant_id=current_user.tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=False,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)
    return IdentitySettingsResponse(
        sso_enabled=bool(identity.sso_enabled),
        allowed_email_domains=list(identity.allowed_email_domains or []),
        sso_federation_enabled=bool(getattr(identity, "sso_federation_enabled", False)),
        sso_federation_mode=str(
            getattr(identity, "sso_federation_mode", "domain") or "domain"
        ),
        sso_federation_provider_id=getattr(
            identity, "sso_federation_provider_id", None
        ),
        scim_enabled=bool(identity.scim_enabled),
        has_scim_token=bool(getattr(identity, "scim_bearer_token", None)),
        scim_last_rotated_at=identity.scim_last_rotated_at.isoformat()
        if identity.scim_last_rotated_at
        else None,
        scim_group_mappings=list(getattr(identity, "scim_group_mappings", None) or []),
    )


@router.get("/identity/diagnostics", response_model=IdentityDiagnosticsResponse)
async def get_identity_diagnostics(
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SSO, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> IdentityDiagnosticsResponse:
    """
    Tenant identity onboarding diagnostics.

    This endpoint helps enterprise admins validate:
    - SSO enforcement configuration (domain allowlist)
    - SCIM provisioning readiness (token + tier + enablement)
    - Token rotation hygiene signals
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))

    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = TenantIdentitySettings(
            tenant_id=current_user.tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=False,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)

    allowed_domains = list(identity.allowed_email_domains or [])
    enforcement_active = bool(identity.sso_enabled and allowed_domains)
    federation_enabled = bool(getattr(identity, "sso_federation_enabled", False))
    federation_mode = (
        str(getattr(identity, "sso_federation_mode", "domain") or "domain")
        .strip()
        .lower()
    )
    if federation_mode not in SUPPORTED_SSO_FEDERATION_MODES:
        federation_mode = "domain"
    provider_id = str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
    email_domain = None
    if getattr(current_user, "email", None):
        value = str(current_user.email or "")
        email_domain = value.split("@")[-1].strip().lower() if "@" in value else None

    sso_issues: list[str] = []
    if bool(identity.sso_enabled) and not allowed_domains:
        sso_issues.append(
            "SSO enforcement is enabled but allowed_email_domains is empty."
        )
    federation_ready = bool(
        federation_enabled
        and (
            federation_mode == "domain"
            or (federation_mode == "provider_id" and bool(provider_id))
        )
    )
    if federation_enabled and federation_mode == "provider_id" and not provider_id:
        sso_issues.append(
            "SSO federation is enabled in provider_id mode but provider_id is not configured."
        )
    if federation_enabled and not bool(identity.sso_enabled):
        sso_issues.append(
            "SSO federation is enabled but SSO allowlist enforcement is disabled."
        )
    current_admin_allowed: bool | None = None
    if enforcement_active:
        current_admin_allowed = bool(
            email_domain
            and email_domain in [str(d).strip().lower() for d in allowed_domains]
        )
        if not current_admin_allowed:
            sso_issues.append(
                "Current admin email domain is not in the allowlist (risk of lockout)."
            )

    scim_available = is_feature_enabled(tier, FeatureFlag.SCIM)
    scim_has_token = bool(getattr(identity, "scim_bearer_token", None))
    scim_bidx_present = bool(getattr(identity, "scim_token_bidx", None))
    scim_last_rotated = identity.scim_last_rotated_at
    token_age_days: int | None = None
    if scim_last_rotated:
        token_age_days = max(
            0,
            int(
                (datetime.now(timezone.utc) - scim_last_rotated).total_seconds()
                // 86400
            ),
        )
    rotation_overdue = bool(
        token_age_days is not None
        and token_age_days > SCIM_TOKEN_ROTATION_RECOMMENDED_DAYS
    )

    scim_issues: list[str] = []
    if bool(identity.scim_enabled) and not scim_available:
        scim_issues.append(
            "SCIM is enabled but not available for this tier (requires Enterprise)."
        )
    if bool(identity.scim_enabled) and scim_available and not scim_has_token:
        scim_issues.append(
            "SCIM is enabled but no SCIM token exists. Rotate the SCIM token."
        )
    if scim_has_token and not scim_bidx_present:
        scim_issues.append(
            "SCIM token blind index is missing. Rotate the SCIM token to restore deterministic lookup."
        )
    if rotation_overdue:
        scim_issues.append(
            "SCIM token rotation is overdue (rotate periodically for hygiene)."
        )

    recommendations: list[str] = []
    if sso_issues:
        recommendations.append(
            "Review SSO enforcement configuration and domain allowlist."
        )
    if scim_issues and scim_available:
        recommendations.append(
            "Review SCIM readiness: ensure SCIM is enabled and rotate a valid token."
        )
    if scim_issues and not scim_available:
        recommendations.append("Upgrade to Enterprise to enable SCIM provisioning.")

    return IdentityDiagnosticsResponse(
        tier=tier.value,
        sso=SsoDiagnostics(
            enabled=bool(identity.sso_enabled),
            allowed_email_domains=allowed_domains,
            enforcement_active=enforcement_active,
            federation_enabled=federation_enabled,
            federation_mode=federation_mode,
            federation_ready=federation_ready,
            current_admin_domain=email_domain,
            current_admin_domain_allowed=current_admin_allowed,
            issues=sso_issues,
        ),
        scim=ScimDiagnostics(
            available=bool(scim_available),
            enabled=bool(identity.scim_enabled),
            has_token=scim_has_token,
            token_blind_index_present=scim_bidx_present,
            last_rotated_at=scim_last_rotated.isoformat()
            if scim_last_rotated
            else None,
            token_age_days=token_age_days,
            rotation_recommended_days=SCIM_TOKEN_ROTATION_RECOMMENDED_DAYS,
            rotation_overdue=rotation_overdue,
            issues=scim_issues,
        ),
        recommendations=recommendations,
    )


@router.get("/identity/sso/validation", response_model=SsoFederationValidationResponse)
async def get_sso_federation_validation(
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SSO, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> SsoFederationValidationResponse:
    """
    Operator-facing SSO federation validation.

    This is intentionally deterministic and "configuration-only": Valdrix does not manage
    the external IdP/provider lifecycle (that is configured in Supabase), but Valdrix
    can validate tenant-scoped settings and compute the expected callback/discovery URLs.
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
    settings = get_settings()

    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = TenantIdentitySettings(
            tenant_id=current_user.tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=False,
        )
        db.add(identity)
        await db.commit()
        await db.refresh(identity)

    allowed_domains = list(identity.allowed_email_domains or [])
    enforcement_active = bool(identity.sso_enabled and allowed_domains)
    federation_enabled = bool(getattr(identity, "sso_federation_enabled", False))
    federation_mode = (
        str(getattr(identity, "sso_federation_mode", "domain") or "domain")
        .strip()
        .lower()
    )
    if federation_mode not in SUPPORTED_SSO_FEDERATION_MODES:
        federation_mode = "domain"
    provider_id = str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
    provider_id_configured = bool(provider_id)

    frontend_url = (
        str(getattr(settings, "FRONTEND_URL", "") or "").strip()
        or "http://localhost:5173"
    )
    api_url = (
        str(getattr(settings, "API_URL", "") or "").strip() or "http://localhost:8000"
    )
    expected_redirect_url = frontend_url.rstrip("/") + "/auth/callback"
    discovery_endpoint = api_url.rstrip("/") + "/api/v1/public/sso/discovery"

    checks: list[SsoFederationValidationCheck] = []

    def add(
        name: str, passed: bool, *, severity: str = "error", detail: str | None = None
    ) -> None:
        checks.append(
            SsoFederationValidationCheck(
                name=name, passed=passed, severity=severity, detail=detail
            )
        )

    add(
        "config.frontend_url_is_http",
        _is_http_url(frontend_url),
        detail="FRONTEND_URL must be a valid http(s) URL.",
    )
    add(
        "config.api_url_is_http",
        _is_http_url(api_url),
        detail="API_URL must be a valid http(s) URL.",
    )
    if bool(getattr(settings, "is_production", False)):
        add(
            "config.frontend_url_is_https_in_production",
            _is_https_url(frontend_url),
            detail="FRONTEND_URL should be https in production.",
        )
        add(
            "config.api_url_is_https_in_production",
            _is_https_url(api_url),
            detail="API_URL should be https in production.",
        )

    if bool(identity.sso_enabled) and not allowed_domains:
        add(
            "sso.allowlist_non_empty_when_enforcement_enabled",
            False,
            detail="SSO enforcement is enabled but allowed_email_domains is empty.",
        )
    else:
        add(
            "sso.allowlist_non_empty_when_enforcement_enabled",
            True,
            severity="info",
            detail="OK",
        )

    if federation_enabled:
        add(
            "sso.federation_requires_enforcement",
            bool(identity.sso_enabled),
            detail="Federated SSO login should not be enabled unless allowlist enforcement is enabled.",
        )
        if federation_mode == "provider_id":
            add(
                "sso.provider_id_required_in_provider_id_mode",
                provider_id_configured,
                detail="sso_federation_provider_id is required when sso_federation_mode=provider_id.",
            )
    else:
        add(
            "sso.federation_enabled",
            False,
            severity="info",
            detail="Federated SSO login is not enabled.",
        )

    # Lockout hygiene: if enforcement is active, ensure current admin domain is allowed.
    if enforcement_active and getattr(current_user, "email", None):
        email_value = str(current_user.email or "")
        email_domain = (
            email_value.split("@")[-1].strip().lower() if "@" in email_value else ""
        )
        add(
            "sso.current_admin_domain_allowed",
            bool(
                email_domain
                and email_domain in [str(d).strip().lower() for d in allowed_domains]
            ),
            severity="warning",
            detail="Current admin email domain should be in allowlist to avoid lockout.",
        )

    # Always include the computed values the operator must add to Supabase allowlists.
    add(
        "supabase.expected_redirect_url_computed",
        True,
        severity="info",
        detail=f"Allow this redirect URL in Supabase SSO provider: {expected_redirect_url}",
    )
    add(
        "valdrix.discovery_endpoint_computed",
        True,
        severity="info",
        detail=f"Login uses tenant-scoped discovery endpoint: {discovery_endpoint}",
    )

    passed = not any((c.severity == "error" and not c.passed) for c in checks)
    return SsoFederationValidationResponse(
        tier=tier.value,
        enforcement_active=enforcement_active,
        federation_enabled=federation_enabled,
        federation_mode=federation_mode,
        provider_id_configured=provider_id_configured,
        frontend_url=frontend_url,
        expected_redirect_url=expected_redirect_url,
        discovery_endpoint=discovery_endpoint,
        passed=passed,
        checks=checks,
    )


@router.post("/identity/scim/test-token", response_model=ScimTokenTestResponse)
async def test_scim_token(
    payload: ScimTokenTestRequest,
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SSO, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> ScimTokenTestResponse:
    """
    Validate the SCIM bearer token currently configured for this tenant.

    This never returns the stored token. It only verifies whether the submitted token matches the tenant-scoped token.
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
    if not is_feature_enabled(tier, FeatureFlag.SCIM):
        raise HTTPException(status_code=403, detail="SCIM requires Enterprise tier.")

    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity or not bool(identity.scim_enabled):
        raise HTTPException(
            status_code=400, detail="SCIM is not enabled for this tenant."
        )
    if not getattr(identity, "scim_token_bidx", None):
        raise HTTPException(
            status_code=400,
            detail="SCIM token is not configured. Rotate the SCIM token first.",
        )

    token_bidx = generate_secret_blind_index(payload.scim_token)
    matches = bool(token_bidx and token_bidx == identity.scim_token_bidx)
    return ScimTokenTestResponse(
        status="ok" if matches else "mismatch", token_matches=matches
    )


@router.put("/identity", response_model=IdentitySettingsResponse)
async def update_identity_settings(
    payload: IdentitySettingsUpdate,
    current_user: CurrentUser = Depends(
        requires_feature(FeatureFlag.SSO, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> IdentitySettingsResponse:
    """
    Update identity settings for this tenant.
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
    if payload.scim_enabled and not is_feature_enabled(tier, FeatureFlag.SCIM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM requires Enterprise tier. Please contact sales.",
        )
    if payload.scim_group_mappings and not is_feature_enabled(tier, FeatureFlag.SCIM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM group mappings require Enterprise tier. Please contact sales.",
        )

    # Guardrail: prevent self-lockout by requiring the current admin's email domain
    # to be in the allowlist when enabling enforcement.
    if payload.sso_enabled and payload.allowed_email_domains:
        email_value = getattr(current_user, "email", "") or ""
        email_domain = (
            email_value.split("@")[-1].strip().lower() if "@" in email_value else ""
        )
        allowed = [
            d.strip().lower() for d in payload.allowed_email_domains if str(d).strip()
        ]
        if not email_domain or email_domain not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "To enable SSO enforcement, include your current email domain in allowed_email_domains "
                    "to avoid locking yourself out."
                ),
            )

    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = TenantIdentitySettings(tenant_id=current_user.tenant_id)
        db.add(identity)

    identity.sso_enabled = bool(payload.sso_enabled)
    identity.allowed_email_domains = list(payload.allowed_email_domains or [])
    identity.sso_federation_enabled = bool(payload.sso_federation_enabled)
    identity.sso_federation_mode = (
        str(payload.sso_federation_mode or "domain").strip().lower()
    )
    identity.sso_federation_provider_id = payload.sso_federation_provider_id

    # Maintain the public SSO domain routing mappings (used by /api/v1/public/sso/discovery).
    desired_domains: list[str] = []
    if bool(identity.sso_enabled) and bool(
        getattr(identity, "sso_federation_enabled", False)
    ):
        desired_domains = [
            str(value).strip().lower().strip(".")
            for value in (identity.allowed_email_domains or [])
            if str(value).strip()
        ]

    if desired_domains:
        # Enforce global uniqueness: one domain can map to at most one tenant.
        conflicts = (
            (
                await db.execute(
                    select(SsoDomainMapping.domain)
                    .where(SsoDomainMapping.domain.in_(desired_domains))
                    .where(SsoDomainMapping.tenant_id != current_user.tenant_id)
                    .where(SsoDomainMapping.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
        if conflicts:
            conflict_list = ", ".join(sorted(set(str(d) for d in conflicts)))
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "One or more allowed_email_domains are already configured for another tenant: "
                    f"{conflict_list}. Remove the domain(s) or contact support."
                ),
            )

    # Replace mappings atomically inside the same transaction.
    await db.execute(
        delete(SsoDomainMapping).where(
            SsoDomainMapping.tenant_id == current_user.tenant_id
        )
    )
    if desired_domains:
        provider_id = (
            str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
            if str(getattr(identity, "sso_federation_mode", "domain") or "domain")
            .strip()
            .lower()
            == "provider_id"
            else None
        )
        for domain in desired_domains:
            db.add(
                SsoDomainMapping(
                    tenant_id=current_user.tenant_id,
                    domain=domain,
                    federation_mode=str(
                        getattr(identity, "sso_federation_mode", "domain") or "domain"
                    )
                    .strip()
                    .lower(),
                    provider_id=provider_id,
                    is_active=True,
                )
            )

    scim_token_generated = False
    if payload.scim_enabled and not identity.scim_bearer_token:
        identity.scim_bearer_token = _generate_scim_token()
        identity.scim_last_rotated_at = datetime.now(timezone.utc)
        scim_token_generated = True
    identity.scim_enabled = bool(payload.scim_enabled)
    identity.scim_group_mappings = [m.model_dump() for m in payload.scim_group_mappings]

    await db.commit()
    await db.refresh(identity)

    # Audit identity settings changes (do not log tokens/secrets).
    try:
        audit = AuditLogger(
            db=db,
            tenant_id=cast(UUID, current_user.tenant_id),
            correlation_id=str(uuid4()),
        )
        await audit.log(
            event_type=AuditEventType.IDENTITY_SETTINGS_UPDATED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="identity_settings",
            resource_id=str(current_user.tenant_id),
            details={
                "sso_enabled": bool(identity.sso_enabled),
                "allowed_email_domains_count": len(
                    identity.allowed_email_domains or []
                ),
                "sso_federation_enabled": bool(
                    getattr(identity, "sso_federation_enabled", False)
                ),
                "sso_federation_mode": str(
                    getattr(identity, "sso_federation_mode", "domain") or "domain"
                ),
                "sso_federation_provider_id_configured": bool(
                    str(
                        getattr(identity, "sso_federation_provider_id", "") or ""
                    ).strip()
                ),
                "scim_enabled": bool(identity.scim_enabled),
                "scim_token_generated": bool(scim_token_generated),
                "scim_last_rotated_at": identity.scim_last_rotated_at.isoformat()
                if identity.scim_last_rotated_at
                else None,
                "scim_group_mappings_count": len(identity.scim_group_mappings or []),
            },
            success=True,
            request_method="PUT",
            request_path="/api/v1/settings/identity",
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - audit logging should never break settings updates
        logger.warning(
            "identity_settings_audit_log_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc),
        )
        await db.rollback()
        # Rollback expires ORM state; refresh so response serialization stays safe.
        try:
            await db.refresh(identity)
        except Exception:
            pass

    logger.info(
        "identity_settings_updated",
        tenant_id=str(current_user.tenant_id),
        sso_enabled=identity.sso_enabled,
        sso_federation_enabled=bool(getattr(identity, "sso_federation_enabled", False)),
        sso_federation_mode=str(
            getattr(identity, "sso_federation_mode", "domain") or "domain"
        ),
        scim_enabled=identity.scim_enabled,
        domains=len(identity.allowed_email_domains or []),
    )

    return IdentitySettingsResponse(
        sso_enabled=bool(identity.sso_enabled),
        allowed_email_domains=list(identity.allowed_email_domains or []),
        sso_federation_enabled=bool(getattr(identity, "sso_federation_enabled", False)),
        sso_federation_mode=str(
            getattr(identity, "sso_federation_mode", "domain") or "domain"
        ),
        sso_federation_provider_id=getattr(
            identity, "sso_federation_provider_id", None
        ),
        scim_enabled=bool(identity.scim_enabled),
        has_scim_token=bool(getattr(identity, "scim_bearer_token", None)),
        scim_last_rotated_at=identity.scim_last_rotated_at.isoformat()
        if identity.scim_last_rotated_at
        else None,
        scim_group_mappings=list(getattr(identity, "scim_group_mappings", None) or []),
    )


@router.post("/identity/rotate-scim-token", response_model=RotateScimTokenResponse)
async def rotate_scim_token(
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> RotateScimTokenResponse:
    """
    Rotate the tenant SCIM bearer token.

    This returns the token ONCE. Store it in your IdP immediately.
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
    if not is_feature_enabled(tier, FeatureFlag.SCIM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM requires Enterprise tier. Please contact sales.",
        )

    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = TenantIdentitySettings(
            tenant_id=current_user.tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=True,
        )
        db.add(identity)

    identity.scim_enabled = True
    token = _generate_scim_token()
    identity.scim_bearer_token = token
    identity.scim_last_rotated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(identity)

    # Audit token rotation without persisting the token value itself.
    try:
        audit = AuditLogger(
            db=db,
            tenant_id=cast(UUID, current_user.tenant_id),
            correlation_id=str(uuid4()),
        )
        await audit.log(
            event_type=AuditEventType.SCIM_TOKEN_ROTATED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="identity_settings",
            resource_id=str(current_user.tenant_id),
            details={
                "rotated_at": identity.scim_last_rotated_at.isoformat()
                if identity.scim_last_rotated_at
                else None,
            },
            success=True,
            request_method="POST",
            request_path="/api/v1/settings/identity/rotate-scim-token",
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "scim_token_rotation_audit_log_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc),
        )
        await db.rollback()
        # Rollback expires ORM state; refresh so response serialization stays safe.
        try:
            await db.refresh(identity)
        except Exception:
            pass

    logger.info("scim_token_rotated", tenant_id=str(current_user.tenant_id))
    return RotateScimTokenResponse(
        scim_token=token, rotated_at=identity.scim_last_rotated_at.isoformat()
    )
