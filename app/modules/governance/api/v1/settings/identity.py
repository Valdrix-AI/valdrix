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
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
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
from app.modules.governance.api.v1.settings.identity_diagnostics_ops import (
    build_identity_diagnostics_payload as _build_identity_diagnostics_payload_impl,
    build_sso_federation_validation_payload as _build_sso_federation_validation_payload_impl,
)
from app.modules.governance.api.v1.settings.identity_settings_ops import (
    rotate_scim_token_route as _rotate_scim_token_route_impl,
    update_identity_settings_route as _update_identity_settings_route_impl,
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
    except (TypeError, ValueError):
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_https_url(value: str) -> bool:
    try:
        parsed = urlparse(str(value or "").strip())
    except (TypeError, ValueError):
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


async def _get_or_create_identity_settings(
    db: AsyncSession, *, tenant_id: UUID
) -> TenantIdentitySettings:
    stmt = select(TenantIdentitySettings).where(
        TenantIdentitySettings.tenant_id == tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if identity:
        return identity

    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        sso_federation_enabled=False,
        sso_federation_mode="domain",
        scim_enabled=False,
    )
    db.add(identity)
    await db.commit()
    await db.refresh(identity)
    return identity


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
        description="Valdrics role to assign when user is in the group: admin|member.",
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
    identity = await _get_or_create_identity_settings(
        db, tenant_id=cast(UUID, current_user.tenant_id)
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
    identity = await _get_or_create_identity_settings(
        db, tenant_id=cast(UUID, current_user.tenant_id)
    )
    payload = _build_identity_diagnostics_payload_impl(
        identity=identity,
        current_user=current_user,
        tier=tier,
        is_feature_enabled_fn=is_feature_enabled,
        scim_feature_flag=FeatureFlag.SCIM,
        rotation_recommended_days=SCIM_TOKEN_ROTATION_RECOMMENDED_DAYS,
        supported_federation_modes=SUPPORTED_SSO_FEDERATION_MODES,
        datetime_cls=datetime,
        timezone_obj=timezone,
    )

    return IdentityDiagnosticsResponse(
        tier=str(payload["tier"]),
        sso=SsoDiagnostics.model_validate(payload["sso"]),
        scim=ScimDiagnostics.model_validate(payload["scim"]),
        recommendations=list(payload.get("recommendations", [])),
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

    This is intentionally deterministic and "configuration-only": Valdrics does not manage
    the external IdP/provider lifecycle (that is configured in Supabase), but Valdrics
    can validate tenant-scoped settings and compute the expected callback/discovery URLs.
    """
    tier = normalize_tier(getattr(current_user, "tier", PricingTier.FREE))
    settings = get_settings()
    identity = await _get_or_create_identity_settings(
        db, tenant_id=cast(UUID, current_user.tenant_id)
    )
    payload = _build_sso_federation_validation_payload_impl(
        identity=identity,
        current_user=current_user,
        tier=tier,
        settings=settings,
        supported_federation_modes=SUPPORTED_SSO_FEDERATION_MODES,
        is_http_url_fn=_is_http_url,
        is_https_url_fn=_is_https_url,
    )
    checks = [
        SsoFederationValidationCheck.model_validate(item)
        for item in payload.get("checks", [])
    ]
    return SsoFederationValidationResponse(
        tier=str(payload["tier"]),
        enforcement_active=bool(payload["enforcement_active"]),
        federation_enabled=bool(payload["federation_enabled"]),
        federation_mode=str(payload["federation_mode"]),
        provider_id_configured=bool(payload["provider_id_configured"]),
        frontend_url=str(payload["frontend_url"]),
        expected_redirect_url=str(payload["expected_redirect_url"]),
        discovery_endpoint=str(payload["discovery_endpoint"]),
        passed=bool(payload["passed"]),
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
    response = await _update_identity_settings_route_impl(
        payload=payload,
        current_user=current_user,
        db=db,
        tenant_identity_settings_model=TenantIdentitySettings,
        sso_domain_mapping_model=SsoDomainMapping,
        feature_flag=FeatureFlag,
        pricing_tier=PricingTier,
        normalize_tier_fn=normalize_tier,
        is_feature_enabled_fn=is_feature_enabled,
        generate_scim_token_fn=_generate_scim_token,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
        logger=logger,
        identity_settings_response_model=IdentitySettingsResponse,
    )
    if isinstance(response, IdentitySettingsResponse):
        return response
    return IdentitySettingsResponse.model_validate(response)


@router.post("/identity/rotate-scim-token", response_model=RotateScimTokenResponse)
async def rotate_scim_token(
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> RotateScimTokenResponse:
    response = await _rotate_scim_token_route_impl(
        current_user=current_user,
        db=db,
        tenant_identity_settings_model=TenantIdentitySettings,
        feature_flag=FeatureFlag,
        pricing_tier=PricingTier,
        normalize_tier_fn=normalize_tier,
        is_feature_enabled_fn=is_feature_enabled,
        generate_scim_token_fn=_generate_scim_token,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
        logger=logger,
        rotate_scim_token_response_model=RotateScimTokenResponse,
    )
    if isinstance(response, RotateScimTokenResponse):
        return response
    return RotateScimTokenResponse.model_validate(response)
