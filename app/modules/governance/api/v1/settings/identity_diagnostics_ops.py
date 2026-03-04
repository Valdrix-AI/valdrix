from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


def build_identity_diagnostics_payload(
    *,
    identity: Any,
    current_user: Any,
    tier: Any,
    is_feature_enabled_fn: Callable[[Any, Any], bool],
    scim_feature_flag: Any,
    rotation_recommended_days: int,
    supported_federation_modes: set[str],
    datetime_cls: type[datetime],
    timezone_obj: Any,
) -> dict[str, Any]:
    allowed_domains = list(getattr(identity, "allowed_email_domains", None) or [])
    enforcement_active = bool(getattr(identity, "sso_enabled", False) and allowed_domains)
    federation_enabled = bool(getattr(identity, "sso_federation_enabled", False))
    federation_mode = str(getattr(identity, "sso_federation_mode", "domain") or "domain").strip().lower()
    if federation_mode not in supported_federation_modes:
        federation_mode = "domain"
    provider_id = str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
    email_domain: str | None = None
    if getattr(current_user, "email", None):
        value = str(getattr(current_user, "email", "") or "")
        email_domain = value.split("@")[-1].strip().lower() if "@" in value else None

    sso_issues: list[str] = []
    if bool(getattr(identity, "sso_enabled", False)) and not allowed_domains:
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
    if federation_enabled and not bool(getattr(identity, "sso_enabled", False)):
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

    scim_available = is_feature_enabled_fn(tier, scim_feature_flag)
    scim_has_token = bool(getattr(identity, "scim_bearer_token", None))
    scim_bidx_present = bool(getattr(identity, "scim_token_bidx", None))
    scim_last_rotated = getattr(identity, "scim_last_rotated_at", None)
    token_age_days: int | None = None
    if scim_last_rotated:
        token_age_days = max(
            0,
            int(
                (
                    datetime_cls.now(timezone_obj.utc) - scim_last_rotated
                ).total_seconds()
                // 86400
            ),
        )
    rotation_overdue = bool(
        token_age_days is not None and token_age_days > rotation_recommended_days
    )

    scim_issues: list[str] = []
    if bool(getattr(identity, "scim_enabled", False)) and not scim_available:
        scim_issues.append(
            "SCIM is enabled but not available for this tier (requires Enterprise)."
        )
    if bool(getattr(identity, "scim_enabled", False)) and scim_available and not scim_has_token:
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

    return {
        "tier": tier.value,
        "sso": {
            "enabled": bool(getattr(identity, "sso_enabled", False)),
            "allowed_email_domains": allowed_domains,
            "enforcement_active": enforcement_active,
            "federation_enabled": federation_enabled,
            "federation_mode": federation_mode,
            "federation_ready": federation_ready,
            "current_admin_domain": email_domain,
            "current_admin_domain_allowed": current_admin_allowed,
            "issues": sso_issues,
        },
        "scim": {
            "available": bool(scim_available),
            "enabled": bool(getattr(identity, "scim_enabled", False)),
            "has_token": scim_has_token,
            "token_blind_index_present": scim_bidx_present,
            "last_rotated_at": scim_last_rotated.isoformat() if scim_last_rotated else None,
            "token_age_days": token_age_days,
            "rotation_recommended_days": rotation_recommended_days,
            "rotation_overdue": rotation_overdue,
            "issues": scim_issues,
        },
        "recommendations": recommendations,
    }


def build_sso_federation_validation_payload(
    *,
    identity: Any,
    current_user: Any,
    tier: Any,
    settings: Any,
    supported_federation_modes: set[str],
    is_http_url_fn: Callable[[str], bool],
    is_https_url_fn: Callable[[str], bool],
) -> dict[str, Any]:
    allowed_domains = list(getattr(identity, "allowed_email_domains", None) or [])
    enforcement_active = bool(getattr(identity, "sso_enabled", False) and allowed_domains)
    federation_enabled = bool(getattr(identity, "sso_federation_enabled", False))
    federation_mode = str(getattr(identity, "sso_federation_mode", "domain") or "domain").strip().lower()
    if federation_mode not in supported_federation_modes:
        federation_mode = "domain"
    provider_id = str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
    provider_id_configured = bool(provider_id)

    frontend_url = str(getattr(settings, "FRONTEND_URL", "") or "").strip() or "http://localhost:5173"
    api_url = str(getattr(settings, "API_URL", "") or "").strip() or "http://localhost:8000"
    expected_redirect_url = frontend_url.rstrip("/") + "/auth/callback"
    discovery_endpoint = api_url.rstrip("/") + "/api/v1/public/sso/discovery"

    checks: list[dict[str, Any]] = []

    def add(
        name: str,
        passed: bool,
        *,
        severity: str = "error",
        detail: str | None = None,
    ) -> None:
        checks.append(
            {"name": name, "passed": passed, "severity": severity, "detail": detail}
        )

    add(
        "config.frontend_url_is_http",
        is_http_url_fn(frontend_url),
        detail="FRONTEND_URL must be a valid http(s) URL.",
    )
    add(
        "config.api_url_is_http",
        is_http_url_fn(api_url),
        detail="API_URL must be a valid http(s) URL.",
    )
    if bool(getattr(settings, "is_production", False)):
        add(
            "config.frontend_url_is_https_in_production",
            is_https_url_fn(frontend_url),
            detail="FRONTEND_URL should be https in production.",
        )
        add(
            "config.api_url_is_https_in_production",
            is_https_url_fn(api_url),
            detail="API_URL should be https in production.",
        )

    if bool(getattr(identity, "sso_enabled", False)) and not allowed_domains:
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
            bool(getattr(identity, "sso_enabled", False)),
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

    if enforcement_active and getattr(current_user, "email", None):
        email_value = str(getattr(current_user, "email", "") or "")
        email_domain = email_value.split("@")[-1].strip().lower() if "@" in email_value else ""
        add(
            "sso.current_admin_domain_allowed",
            bool(
                email_domain
                and email_domain in [str(d).strip().lower() for d in allowed_domains]
            ),
            severity="warning",
            detail="Current admin email domain should be in allowlist to avoid lockout.",
        )

    add(
        "supabase.expected_redirect_url_computed",
        True,
        severity="info",
        detail=f"Allow this redirect URL in Supabase SSO provider: {expected_redirect_url}",
    )
    add(
        "valdrics.discovery_endpoint_computed",
        True,
        severity="info",
        detail=f"Login uses tenant-scoped discovery endpoint: {discovery_endpoint}",
    )

    passed = not any((c["severity"] == "error" and not c["passed"]) for c in checks)
    return {
        "tier": tier.value,
        "enforcement_active": enforcement_active,
        "federation_enabled": federation_enabled,
        "federation_mode": federation_mode,
        "provider_id_configured": provider_id_configured,
        "frontend_url": frontend_url,
        "expected_redirect_url": expected_redirect_url,
        "discovery_endpoint": discovery_endpoint,
        "passed": passed,
        "checks": checks,
    }
