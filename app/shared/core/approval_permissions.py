from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant_identity_settings import TenantIdentitySettings

logger = structlog.get_logger()

APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD = "remediation.approve.nonprod"
APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD = "remediation.approve.prod"

SUPPORTED_APPROVAL_PERMISSIONS = frozenset(
    {
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD,
        APPROVAL_PERMISSION_REMEDIATION_APPROVE_PROD,
    }
)


def normalize_approval_permission(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in SUPPORTED_APPROVAL_PERMISSIONS:
        return normalized
    return None


def normalize_approval_permissions(values: Iterable[Any] | None) -> list[str]:
    normalized: list[str] = []
    if values is None:
        return normalized

    for value in values:
        permission = normalize_approval_permission(value)
        if not permission:
            continue
        if permission not in normalized:
            normalized.append(permission)
    return normalized


def role_default_approval_permissions(role: Any) -> set[str]:
    role_value = str(getattr(role, "value", role) or "").strip().lower()
    if role_value == "owner":
        return set(SUPPORTED_APPROVAL_PERMISSIONS)
    if role_value == "admin":
        return {APPROVAL_PERMISSION_REMEDIATION_APPROVE_NONPROD}
    return set()


async def _load_scim_group_mappings(
    db: AsyncSession,
    tenant_id: UUID,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TenantIdentitySettings.scim_group_mappings).where(
            TenantIdentitySettings.tenant_id == tenant_id
        )
    )
    raw = result.scalar_one_or_none()
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


async def _load_user_group_names(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> set[str]:
    rows = (
        await db.execute(
            select(ScimGroup.display_name_norm)
            .join(ScimGroupMember, ScimGroupMember.group_id == ScimGroup.id)
            .where(ScimGroupMember.tenant_id == tenant_id)
            .where(ScimGroup.tenant_id == tenant_id)
            .where(ScimGroupMember.user_id == user_id)
        )
    ).all()
    return {str(row[0] or "").strip().lower() for row in rows if row and row[0]}


async def _load_scim_approval_permissions(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
) -> set[str]:
    mappings = await _load_scim_group_mappings(db, tenant_id)
    if not mappings:
        return set()

    group_names = await _load_user_group_names(db, tenant_id, user_id)
    if not group_names:
        return set()

    permissions: set[str] = set()
    for mapping in mappings:
        group = str(mapping.get("group", "")).strip().lower()
        if not group or group not in group_names:
            continue
        permissions.update(normalize_approval_permissions(mapping.get("permissions")))
    return permissions


async def user_has_approval_permission(
    db: AsyncSession,
    user: Any,
    required_permission: str,
) -> bool:
    normalized_required = normalize_approval_permission(required_permission)
    if not normalized_required:
        return False

    default_permissions = role_default_approval_permissions(getattr(user, "role", None))
    if normalized_required in default_permissions:
        return True

    tenant_id = getattr(user, "tenant_id", None)
    user_id = getattr(user, "id", None)
    if not isinstance(tenant_id, UUID) or not isinstance(user_id, UUID):
        return False

    try:
        scim_permissions = await _load_scim_approval_permissions(db, tenant_id, user_id)
    except Exception as exc:
        logger.exception(
            "approval_permission_resolution_failed",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            required_permission=normalized_required,
            error=str(exc),
        )
        return False

    return normalized_required in scim_permissions

