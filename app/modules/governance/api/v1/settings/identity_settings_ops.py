from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


def build_identity_response_payload(identity: Any) -> dict[str, Any]:
    return {
        "sso_enabled": bool(identity.sso_enabled),
        "allowed_email_domains": list(identity.allowed_email_domains or []),
        "sso_federation_enabled": bool(
            getattr(identity, "sso_federation_enabled", False)
        ),
        "sso_federation_mode": str(
            getattr(identity, "sso_federation_mode", "domain") or "domain"
        ),
        "sso_federation_provider_id": getattr(
            identity,
            "sso_federation_provider_id",
            None,
        ),
        "scim_enabled": bool(identity.scim_enabled),
        "has_scim_token": bool(getattr(identity, "scim_bearer_token", None)),
        "scim_last_rotated_at": identity.scim_last_rotated_at.isoformat()
        if identity.scim_last_rotated_at
        else None,
        "scim_group_mappings": list(
            getattr(identity, "scim_group_mappings", None) or []
        ),
    }


async def update_identity_settings_route(
    *,
    payload: Any,
    current_user: Any,
    db: AsyncSession,
    tenant_identity_settings_model: Any,
    sso_domain_mapping_model: Any,
    feature_flag: Any,
    pricing_tier: Any,
    normalize_tier_fn: Any,
    is_feature_enabled_fn: Any,
    generate_scim_token_fn: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
    logger: Any,
    identity_settings_response_model: Any,
) -> Any:
    tier = normalize_tier_fn(getattr(current_user, "tier", pricing_tier.FREE))
    if payload.scim_enabled and not is_feature_enabled_fn(tier, feature_flag.SCIM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM requires Enterprise tier. Please contact sales.",
        )
    if payload.scim_group_mappings and not is_feature_enabled_fn(
        tier,
        feature_flag.SCIM,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM group mappings require Enterprise tier. Please contact sales.",
        )

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
                    "To enable SSO enforcement, include your current email domain in "
                    "allowed_email_domains to avoid locking yourself out."
                ),
            )

    stmt = select(tenant_identity_settings_model).where(
        tenant_identity_settings_model.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = tenant_identity_settings_model(tenant_id=current_user.tenant_id)
        db.add(identity)

    identity.sso_enabled = bool(payload.sso_enabled)
    identity.allowed_email_domains = list(payload.allowed_email_domains or [])
    identity.sso_federation_enabled = bool(payload.sso_federation_enabled)
    identity.sso_federation_mode = (
        str(payload.sso_federation_mode or "domain").strip().lower()
    )
    identity.sso_federation_provider_id = payload.sso_federation_provider_id

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
        conflicts = (
            (
                await db.execute(
                    select(sso_domain_mapping_model.domain)
                    .where(sso_domain_mapping_model.domain.in_(desired_domains))
                    .where(sso_domain_mapping_model.tenant_id != current_user.tenant_id)
                    .where(sso_domain_mapping_model.is_active.is_(True))
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
                    "One or more allowed_email_domains are already configured for "
                    f"another tenant: {conflict_list}. Remove the domain(s) or "
                    "contact support."
                ),
            )

    await db.execute(
        delete(sso_domain_mapping_model).where(
            sso_domain_mapping_model.tenant_id == current_user.tenant_id
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
                sso_domain_mapping_model(
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
        identity.scim_bearer_token = generate_scim_token_fn()
        identity.scim_last_rotated_at = datetime.now(timezone.utc)
        scim_token_generated = True
    identity.scim_enabled = bool(payload.scim_enabled)
    identity.scim_group_mappings = [m.model_dump() for m in payload.scim_group_mappings]

    await db.commit()
    await db.refresh(identity)

    try:
        audit = audit_logger_cls(
            db=db,
            tenant_id=cast(UUID, current_user.tenant_id),
            correlation_id=str(uuid4()),
        )
        await audit.log(
            event_type=audit_event_type.IDENTITY_SETTINGS_UPDATED,
            actor_id=current_user.id,
            actor_email=current_user.email,
            resource_type="identity_settings",
            resource_id=str(current_user.tenant_id),
            details={
                "sso_enabled": bool(identity.sso_enabled),
                "allowed_email_domains_count": len(identity.allowed_email_domains or []),
                "sso_federation_enabled": bool(
                    getattr(identity, "sso_federation_enabled", False)
                ),
                "sso_federation_mode": str(
                    getattr(identity, "sso_federation_mode", "domain") or "domain"
                ),
                "sso_federation_provider_id_configured": bool(
                    str(getattr(identity, "sso_federation_provider_id", "") or "").strip()
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
    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
        logger.warning(
            "identity_settings_audit_log_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc),
        )
        await db.rollback()
        try:
            await db.refresh(identity)
        except (RuntimeError, ValueError, TypeError, AttributeError):
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

    return identity_settings_response_model(**build_identity_response_payload(identity))


async def rotate_scim_token_route(
    *,
    current_user: Any,
    db: AsyncSession,
    tenant_identity_settings_model: Any,
    feature_flag: Any,
    pricing_tier: Any,
    normalize_tier_fn: Any,
    is_feature_enabled_fn: Any,
    generate_scim_token_fn: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
    logger: Any,
    rotate_scim_token_response_model: Any,
) -> Any:
    tier = normalize_tier_fn(getattr(current_user, "tier", pricing_tier.FREE))
    if not is_feature_enabled_fn(tier, feature_flag.SCIM):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SCIM requires Enterprise tier. Please contact sales.",
        )

    stmt = select(tenant_identity_settings_model).where(
        tenant_identity_settings_model.tenant_id == current_user.tenant_id
    )
    identity = (await db.execute(stmt)).scalar_one_or_none()
    if not identity:
        identity = tenant_identity_settings_model(
            tenant_id=current_user.tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            sso_federation_enabled=False,
            sso_federation_mode="domain",
            scim_enabled=True,
        )
        db.add(identity)

    identity.scim_enabled = True
    token = generate_scim_token_fn()
    identity.scim_bearer_token = token
    identity.scim_last_rotated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(identity)

    try:
        audit = audit_logger_cls(
            db=db,
            tenant_id=cast(UUID, current_user.tenant_id),
            correlation_id=str(uuid4()),
        )
        await audit.log(
            event_type=audit_event_type.SCIM_TOKEN_ROTATED,
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
    except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
        logger.warning(
            "scim_token_rotation_audit_log_failed",
            tenant_id=str(current_user.tenant_id),
            error=str(exc),
        )
        await db.rollback()
        try:
            await db.refresh(identity)
        except (RuntimeError, ValueError, TypeError, AttributeError):
            pass

    logger.info("scim_token_rotated", tenant_id=str(current_user.tenant_id))
    return rotate_scim_token_response_model(
        scim_token=token,
        rotated_at=identity.scim_last_rotated_at.isoformat(),
    )
