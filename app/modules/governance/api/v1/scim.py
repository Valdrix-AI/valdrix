"""
SCIM 2.0 (Minimal) Provisioning API.

Goals:
- Enterprise-only, tenant-scoped provisioning (create/disable/update users)
- No dependency on browser cookies/CSRF (Bearer token auth)
- Deterministic lookup via blind index (no decrypt required for auth)

Supported resources:
- Users
- Groups (optional, for IdPs that manage membership via /Groups)
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, User, UserPersona, UserRole
from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.shared.core.pricing import FeatureFlag, is_feature_enabled, normalize_tier
from app.shared.core.security import generate_secret_blind_index
from app.shared.db import session as db_session

logger = structlog.get_logger()
router = APIRouter(tags=["SCIM"])

# SCIM schemas / message constants
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_SCHEMA_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"


def _scim_user_schema_resource(*, base_url: str) -> dict[str, Any]:
    # Minimal schema definition sufficient for IdP discovery.
    return {
        "schemas": [SCIM_SCHEMA_SCHEMA],
        "id": SCIM_USER_SCHEMA,
        "name": "User",
        "description": "Valdrix user account",
        "attributes": [
            {
                "name": "userName",
                "type": "string",
                "multiValued": False,
                "required": True,
                "caseExact": False,
                "mutability": "readWrite",
                "returned": "default",
            },
            {
                "name": "active",
                "type": "boolean",
                "multiValued": False,
                "required": False,
                "mutability": "readWrite",
                "returned": "default",
            },
            {
                "name": "emails",
                "type": "complex",
                "multiValued": True,
                "required": False,
                "mutability": "readWrite",
                "returned": "default",
                "subAttributes": [
                    {
                        "name": "value",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "primary",
                        "type": "boolean",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "type",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                ],
            },
            {
                # We accept `groups` in user payloads and also support Group resources for IdPs
                # that manage membership via /Groups.
                "name": "groups",
                "type": "complex",
                "multiValued": True,
                "required": False,
                "mutability": "readWrite",
                "returned": "default",
                "subAttributes": [
                    {
                        "name": "value",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "display",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                ],
            },
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base_url.rstrip('/')}/scim/v2/Schemas/{SCIM_USER_SCHEMA}",
        },
    }


def _scim_group_schema_resource(*, base_url: str) -> dict[str, Any]:
    # Minimal schema definition sufficient for IdP discovery.
    return {
        "schemas": [SCIM_SCHEMA_SCHEMA],
        "id": SCIM_GROUP_SCHEMA,
        "name": "Group",
        "description": "Valdrix SCIM group",
        "attributes": [
            {
                "name": "displayName",
                "type": "string",
                "multiValued": False,
                "required": True,
                "caseExact": False,
                "mutability": "readWrite",
                "returned": "default",
            },
            {
                "name": "externalId",
                "type": "string",
                "multiValued": False,
                "required": False,
                "caseExact": False,
                "mutability": "readWrite",
                "returned": "default",
            },
            {
                "name": "members",
                "type": "complex",
                "multiValued": True,
                "required": False,
                "mutability": "readWrite",
                "returned": "default",
                "subAttributes": [
                    {
                        "name": "value",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                    {
                        "name": "display",
                        "type": "string",
                        "multiValued": False,
                        "required": False,
                    },
                ],
            },
        ],
        "meta": {
            "resourceType": "Schema",
            "location": f"{base_url.rstrip('/')}/scim/v2/Schemas/{SCIM_GROUP_SCHEMA}",
        },
    }


class ScimError(Exception):
    def __init__(
        self, status_code: int, detail: str, *, scim_type: str | None = None
    ) -> None:
        super().__init__(detail)
        self.status_code = int(status_code)
        self.detail = str(detail)
        self.scim_type = scim_type


def scim_error_response(exc: ScimError) -> JSONResponse:
    payload: dict[str, Any] = {
        "schemas": [SCIM_ERROR_SCHEMA],
        "status": str(exc.status_code),
        "detail": exc.detail,
    }
    if exc.scim_type:
        payload["scimType"] = exc.scim_type
    return JSONResponse(
        status_code=exc.status_code,
        content=payload,
        headers={"WWW-Authenticate": "Bearer"},
    )


@dataclass(frozen=True, slots=True)
class ScimContext:
    tenant_id: UUID


def _extract_bearer_token(request: Request) -> str:
    raw = (request.headers.get("Authorization") or "").strip()
    if not raw.lower().startswith("bearer "):
        raise ScimError(
            401, "Missing or invalid Authorization header", scim_type="invalidSyntax"
        )
    token = raw.split(" ", 1)[-1].strip()
    if not token:
        raise ScimError(401, "Missing bearer token", scim_type="invalidSyntax")
    return token


async def get_scim_context(request: Request) -> ScimContext:
    token = _extract_bearer_token(request)
    token_bidx = generate_secret_blind_index(token)
    if not token_bidx:
        raise ScimError(401, "Invalid bearer token", scim_type="invalidSyntax")

    # NOTE: We intentionally reference `db_session.async_session_maker` at runtime so
    # tests can patch it to a per-test engine (instead of capturing the symbol at import).
    async with db_session.async_session_maker() as db:
        result = await db.execute(
            select(
                TenantIdentitySettings.tenant_id, TenantIdentitySettings.scim_enabled
            ).where(TenantIdentitySettings.scim_token_bidx == token_bidx)
        )
        row = result.first()
        if not row:
            raise ScimError(401, "Unauthorized", scim_type="invalidToken")

        tenant_id, scim_enabled = row
        if not bool(scim_enabled):
            raise ScimError(
                403, "SCIM is disabled for this tenant", scim_type="forbidden"
            )

        tenant_plan = (
            await db.execute(select(Tenant.plan).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
        tier = normalize_tier(tenant_plan)
        if not is_feature_enabled(tier, FeatureFlag.SCIM):
            raise ScimError(403, "SCIM requires Enterprise tier", scim_type="forbidden")

        request.state.tenant_id = tenant_id
        return ScimContext(tenant_id=tenant_id)


async def get_scim_db(
    ctx: ScimContext = Depends(get_scim_context),
) -> AsyncGenerator[AsyncSession, None]:
    # We use a fresh session that we control, and set tenant context before touching tenant tables.
    async with db_session.async_session_maker() as db:
        await db_session.set_session_tenant_id(db, ctx.tenant_id)
        yield db


def _scim_user_resource(
    user: User,
    *,
    base_url: str,
    tenant_id: UUID,
    groups: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # Build minimal SCIM User representation.
    payload: dict[str, Any] = {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "userName": str(user.email),
        "active": bool(getattr(user, "is_active", True)),
        "emails": [{"value": str(user.email), "primary": True}],
        "meta": {
            "resourceType": "User",
            "location": f"{base_url.rstrip('/')}/scim/v2/Users/{user.id}",
        },
    }
    if groups is not None:
        payload["groups"] = groups
    return payload


def _scim_group_resource(
    group: ScimGroup,
    *,
    base_url: str,
    members: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": str(group.id),
        "displayName": str(getattr(group, "display_name", "") or ""),
        "meta": {
            "resourceType": "Group",
            "location": f"{base_url.rstrip('/')}/scim/v2/Groups/{group.id}",
        },
    }
    if getattr(group, "external_id", None):
        payload["externalId"] = str(group.external_id)
    if members is not None:
        payload["members"] = members
    return payload


async def _load_user_group_refs_map(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: list[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    if not user_ids:
        return {}

    rows = (
        await db.execute(
            select(ScimGroupMember.user_id, ScimGroup.id, ScimGroup.display_name)
            .join(ScimGroup, ScimGroupMember.group_id == ScimGroup.id)
            .where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroup.tenant_id == tenant_id,
                ScimGroupMember.user_id.in_(user_ids),
            )
        )
    ).all()
    mapping: dict[UUID, list[dict[str, Any]]] = {uid: [] for uid in user_ids}
    for user_id, group_id, display_name in rows:
        mapping.setdefault(user_id, []).append(
            {"value": str(group_id), "display": str(display_name or "")}
        )
    return mapping


async def _load_group_member_refs_map(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    group_ids: list[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    if not group_ids:
        return {}

    rows = (
        await db.execute(
            select(ScimGroupMember.group_id, User.id, User.email)
            .join(User, ScimGroupMember.user_id == User.id)
            .where(
                ScimGroupMember.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                ScimGroupMember.group_id.in_(group_ids),
            )
        )
    ).all()
    mapping: dict[UUID, list[dict[str, Any]]] = {gid: [] for gid in group_ids}
    for group_id, user_id, email in rows:
        mapping.setdefault(group_id, []).append(
            {"value": str(user_id), "display": str(email or "")}
        )
    return mapping


class ScimListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_LIST_SCHEMA])
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[dict[str, Any]]

    model_config = ConfigDict(extra="forbid")


class ScimEmail(BaseModel):
    value: EmailStr
    primary: bool | None = None
    type: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupRef(BaseModel):
    value: str | None = None
    display: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimMemberRef(BaseModel):
    value: str | None = None
    display: str | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupCreate(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)
    externalId: str | None = Field(default=None, max_length=255)
    members: list[ScimMemberRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimGroupPut(BaseModel):
    displayName: str = Field(min_length=1, max_length=255)
    externalId: str | None = Field(default=None, max_length=255)
    members: list[ScimMemberRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimUserCreate(BaseModel):
    userName: EmailStr
    active: bool = True
    emails: list[ScimEmail] | None = None
    groups: list[ScimGroupRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimUserPut(BaseModel):
    userName: EmailStr
    active: bool = True
    emails: list[ScimEmail] | None = None
    groups: list[ScimGroupRef] | None = None

    model_config = ConfigDict(extra="ignore")


class ScimPatchOperation(BaseModel):
    op: Literal["add", "replace", "remove"]
    path: str | None = None
    value: Any | None = None

    model_config = ConfigDict(extra="ignore")


class ScimPatchRequest(BaseModel):
    Operations: list[ScimPatchOperation] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


def _normalize_scim_group(value: str) -> str:
    return str(value or "").strip().lower()


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


async def _get_or_create_scim_group(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    display_name: str,
    external_id: str | None = None,
) -> ScimGroup:
    display = str(display_name or "").strip()
    if not display:
        raise ScimError(400, "displayName is required", scim_type="invalidValue")
    display_norm = _normalize_scim_group(display)
    external_norm = _normalize_scim_group(external_id or "") or None

    existing = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == tenant_id,
                ScimGroup.display_name_norm == display_norm,
            )
        )
    ).scalar_one_or_none()
    if existing:
        # Keep displayName up to date for IdP-driven renames.
        existing.display_name = display
        existing.display_name_norm = display_norm
        if external_id:
            existing.external_id = external_id
            existing.external_id_norm = external_norm
        return existing

    group = ScimGroup(
        id=uuid4(),
        tenant_id=tenant_id,
        display_name=display,
        display_name_norm=display_norm,
        external_id=external_id,
        external_id_norm=external_norm,
    )
    # Race-safe without rolling back the outer transaction: use a SAVEPOINT.
    try:
        async with db.begin_nested():
            db.add(group)
            await db.flush()
        return group
    except IntegrityError:
        existing = (
            await db.execute(
                select(ScimGroup).where(
                    ScimGroup.tenant_id == tenant_id,
                    ScimGroup.display_name_norm == display_norm,
                )
            )
        ).scalar_one()
        return existing


async def _resolve_groups_from_refs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    groups: list[ScimGroupRef],
) -> tuple[set[UUID], set[str]]:
    group_ids: set[UUID] = set()
    group_names_norm: set[str] = set()

    for ref in groups:
        display = str(ref.display or "").strip()
        raw_value = str(ref.value or "").strip()

        if not display and not raw_value:
            continue

        if display:
            group = await _get_or_create_scim_group(
                db, tenant_id=tenant_id, display_name=display
            )
        else:
            parsed = _parse_uuid(raw_value)
            if parsed is not None:
                group = (
                    await db.execute(
                        select(ScimGroup).where(
                            ScimGroup.tenant_id == tenant_id,
                            ScimGroup.id == parsed,
                        )
                    )
                ).scalar_one_or_none()
                if group is None:
                    # No group push yet; treat the value as a stable "name" so mappings can still match it.
                    group = await _get_or_create_scim_group(
                        db, tenant_id=tenant_id, display_name=raw_value
                    )
            else:
                group = await _get_or_create_scim_group(
                    db, tenant_id=tenant_id, display_name=raw_value
                )

        group_ids.add(group.id)
        group_names_norm.add(
            str(
                getattr(group, "display_name_norm", "")
                or _normalize_scim_group(group.display_name)
            )
        )

    return group_ids, group_names_norm


async def _resolve_member_user_ids(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    members: list[ScimMemberRef],
) -> set[UUID]:
    candidate_ids: set[UUID] = set()
    for ref in members:
        parsed = _parse_uuid(ref.value)
        if parsed is not None:
            candidate_ids.add(parsed)

    if not candidate_ids:
        return set()

    rows = (
        await db.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.id.in_(list(candidate_ids)),
            )
        )
    ).all()
    return {row[0] for row in rows if row and row[0]}


async def _load_group_member_user_ids(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    group_id: UUID,
) -> set[UUID]:
    rows = (
        await db.execute(
            select(ScimGroupMember.user_id).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.group_id == group_id,
            )
        )
    ).all()
    return {row[0] for row in rows if row and row[0]}


async def _set_user_group_memberships(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    group_ids: set[UUID],
) -> None:
    existing_rows = (
        await db.execute(
            select(ScimGroupMember.group_id).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.user_id == user_id,
            )
        )
    ).all()
    existing = {row[0] for row in existing_rows if row and row[0]}

    to_remove = existing - group_ids
    to_add = group_ids - existing

    if to_remove:
        await db.execute(
            delete(ScimGroupMember).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.user_id == user_id,
                ScimGroupMember.group_id.in_(list(to_remove)),
            )
        )

    for gid in sorted(to_add, key=lambda x: str(x)):
        db.add(
            ScimGroupMember(
                id=uuid4(),
                tenant_id=tenant_id,
                group_id=gid,
                user_id=user_id,
            )
        )


async def _set_group_memberships(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    group_id: UUID,
    member_user_ids: set[UUID],
) -> set[UUID]:
    existing_rows = (
        await db.execute(
            select(ScimGroupMember.user_id).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.group_id == group_id,
            )
        )
    ).all()
    existing = {row[0] for row in existing_rows if row and row[0]}

    to_remove = existing - member_user_ids
    to_add = member_user_ids - existing

    if to_remove:
        await db.execute(
            delete(ScimGroupMember).where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroupMember.group_id == group_id,
                ScimGroupMember.user_id.in_(list(to_remove)),
            )
        )

    for uid in sorted(to_add, key=lambda x: str(x)):
        db.add(
            ScimGroupMember(
                id=uuid4(),
                tenant_id=tenant_id,
                group_id=group_id,
                user_id=uid,
            )
        )

    return existing | member_user_ids


async def _load_scim_group_mappings(
    db: AsyncSession, tenant_id: UUID
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TenantIdentitySettings.scim_group_mappings).where(
            TenantIdentitySettings.tenant_id == tenant_id
        )
    )
    raw = result.scalar_one_or_none()
    if not raw:
        return []
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, dict)]
    return []


def _resolve_entitlements_from_groups(
    group_names: set[str],
    mappings: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    desired_role: str | None = None
    desired_persona: str | None = None

    for mapping in mappings:
        group = _normalize_scim_group(mapping.get("group", ""))
        if not group or group not in group_names:
            continue

        role = _normalize_scim_group(mapping.get("role", ""))
        if role == UserRole.ADMIN.value:
            desired_role = UserRole.ADMIN.value
        elif desired_role is None and role == UserRole.MEMBER.value:
            desired_role = UserRole.MEMBER.value

        persona = _normalize_scim_group(mapping.get("persona", ""))
        if desired_persona is None and persona in {
            UserPersona.ENGINEERING.value,
            UserPersona.FINANCE.value,
            UserPersona.PLATFORM.value,
            UserPersona.LEADERSHIP.value,
        }:
            desired_persona = persona

    return desired_role, desired_persona


async def _load_user_group_names_from_memberships(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
) -> set[str]:
    rows = (
        await db.execute(
            select(ScimGroup.display_name_norm)
            .join(ScimGroupMember, ScimGroupMember.group_id == ScimGroup.id)
            .where(
                ScimGroupMember.tenant_id == tenant_id,
                ScimGroup.tenant_id == tenant_id,
                ScimGroupMember.user_id == user_id,
            )
        )
    ).all()
    return {str(row[0] or "") for row in rows if row and row[0]}


async def _recompute_entitlements_for_users(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: set[UUID],
) -> None:
    if not user_ids:
        return

    mappings = await _load_scim_group_mappings(db, tenant_id)

    for uid in sorted(user_ids, key=lambda x: str(x)):
        user = (
            await db.execute(
                select(User).where(User.tenant_id == tenant_id, User.id == uid)
            )
        ).scalar_one_or_none()
        if not user:
            continue
        current_role = _normalize_scim_group(getattr(user, "role", ""))
        if current_role == UserRole.OWNER.value:
            continue

        group_names = await _load_user_group_names_from_memberships(
            db, tenant_id=tenant_id, user_id=uid
        )
        desired_role, desired_persona = _resolve_entitlements_from_groups(
            group_names, mappings
        )

        user.role = desired_role or UserRole.MEMBER.value
        if desired_persona:
            user.persona = desired_persona


async def _apply_scim_group_mappings(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user: User,
    groups: list[ScimGroupRef] | None,
    for_create: bool,
) -> None:
    """
    Apply SCIM group entitlements (role/persona) based on tenant-configured mappings.

    - If groups is omitted (None), we do not change entitlements on update.
    - If groups is present (even empty), it is authoritative: missing mappings demote to member.
    - Owners are never demoted by SCIM (guardrail).
    """
    current_role = _normalize_scim_group(getattr(user, "role", ""))
    if current_role == UserRole.OWNER.value:
        return

    if groups is None:
        if for_create:
            user.role = UserRole.MEMBER.value
            user.persona = (
                getattr(user, "persona", None) or UserPersona.ENGINEERING.value
            )
        return

    group_ids, group_names = await _resolve_groups_from_refs(
        db, tenant_id=tenant_id, groups=groups
    )
    await _set_user_group_memberships(
        db, tenant_id=tenant_id, user_id=user.id, group_ids=group_ids
    )

    mappings = await _load_scim_group_mappings(db, tenant_id)
    desired_role, desired_persona = _resolve_entitlements_from_groups(
        group_names, mappings
    )

    # Role is security-sensitive: when groups is present, treat as authoritative.
    user.role = desired_role or UserRole.MEMBER.value

    # Persona is UX-only: only set when mapping provides an explicit persona.
    if desired_persona:
        user.persona = desired_persona
    elif for_create and not getattr(user, "persona", None):
        user.persona = UserPersona.ENGINEERING.value


@router.get("/ServiceProviderConfig")
async def get_service_provider_config() -> dict[str, Any]:
    # Minimal ServiceProviderConfig for IdP compatibility.
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "Tenant-scoped SCIM bearer token",
                "specUri": "https://www.rfc-editor.org/rfc/rfc6750",
            }
        ],
    }


@router.get("/Schemas")
async def list_schemas(request: Request) -> dict[str, Any]:
    base_url = str(request.base_url).rstrip("/")
    resources = [
        _scim_user_schema_resource(base_url=base_url),
        _scim_group_schema_resource(base_url=base_url),
    ]
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": len(resources),
        "startIndex": 1,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


@router.get("/Schemas/{schema_id:path}")
async def get_schema(request: Request, schema_id: str) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    normalized = (schema_id or "").strip()
    if normalized == SCIM_USER_SCHEMA:
        return JSONResponse(
            status_code=200, content=_scim_user_schema_resource(base_url=base_url)
        )
    if normalized == SCIM_GROUP_SCHEMA:
        return JSONResponse(
            status_code=200, content=_scim_group_schema_resource(base_url=base_url)
        )
    raise ScimError(404, "Resource not found")


@router.get("/ResourceTypes")
async def get_resource_types() -> dict[str, Any]:
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": 2,
        "startIndex": 1,
        "itemsPerPage": 2,
        "Resources": [
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "User",
                "name": "User",
                "endpoint": "/Users",
                "schema": SCIM_USER_SCHEMA,
            },
            {
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ResourceType"],
                "id": "Group",
                "name": "Group",
                "endpoint": "/Groups",
                "schema": SCIM_GROUP_SCHEMA,
            },
        ],
    }


def _parse_user_filter(filter_value: str) -> str | None:
    # Support: userName eq "email@domain.com"
    filter_value = (filter_value or "").strip()
    if not filter_value:
        return None
    m = re.match(r'(?i)^userName\s+eq\s+"([^"]+)"\s*$', filter_value)
    if m:
        return m.group(1).strip()
    m = re.match(r"(?i)^userName\s+eq\s+([^\s]+)\s*$", filter_value)
    if m:
        return m.group(1).strip().strip('"')
    return None


def _parse_group_filter(filter_value: str) -> tuple[str, str] | None:
    """
    Support:
    - displayName eq "Group Name"
    - externalId eq "idp-external-id"
    """
    filter_value = (filter_value or "").strip()
    if not filter_value:
        return None

    for attr in ("displayName", "externalId"):
        m = re.match(rf'(?i)^{attr}\s+eq\s+"([^"]+)"\s*$', filter_value)
        if m:
            return (attr, m.group(1).strip())
        m = re.match(rf"(?i)^{attr}\s+eq\s+([^\s]+)\s*$", filter_value)
        if m:
            return (attr, m.group(1).strip().strip('"'))
    return None


@router.get("/Users")
async def list_users(
    request: Request,
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> ScimListResponse:
    if startIndex < 1:
        raise ScimError(400, "startIndex must be >= 1", scim_type="invalidValue")
    if count < 0 or count > 200:
        raise ScimError(
            400, "count must be between 0 and 200", scim_type="invalidValue"
        )

    stmt = select(User).where(User.tenant_id == ctx.tenant_id)
    email_filter = _parse_user_filter(filter or "")
    if filter and email_filter is None:
        raise ScimError(400, "Unsupported filter expression", scim_type="invalidFilter")
    if email_filter:
        stmt = stmt.where(User.email == email_filter)

    result = await db.execute(stmt)
    users = list(result.scalars().all())
    total = len(users)
    start = startIndex - 1
    end = start + count if count else start
    page = users[start:end]

    base_url = str(request.base_url).rstrip("/")
    group_map = await _load_user_group_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        user_ids=[item.id for item in page],
    )
    resources = [
        _scim_user_resource(
            item,
            base_url=base_url,
            tenant_id=ctx.tenant_id,
            groups=group_map.get(item.id, []),
        )
        for item in page
    ]
    return ScimListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(page),
        Resources=resources,
    )


@router.post("/Users")
async def create_user(
    request: Request,
    body: ScimUserCreate,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    user = User(
        id=uuid4(),
        tenant_id=ctx.tenant_id,
        email=str(body.userName),
        role=UserRole.MEMBER.value,
        is_active=bool(body.active),
    )
    db.add(user)
    # Ensure FK-safe inserts for group membership rows.
    await db.flush()
    # Apply tenant-configured entitlements and membership (if groups provided).
    await _apply_scim_group_mappings(
        db,
        tenant_id=ctx.tenant_id,
        user=user,
        groups=body.groups,
        for_create=True,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "User already exists", scim_type="uniqueness") from exc

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_USER_CREATED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={
            "email": str(user.email),
            "active": bool(user.is_active),
            "role": str(getattr(user, "role", "")),
            "persona": str(getattr(user, "persona", ""))
            if getattr(user, "persona", None)
            else None,
            "groups_provided": body.groups is not None,
            "groups_count": len(body.groups or []),
        },
        request_method="SCIM",
        request_path="/scim/v2/Users",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    group_map = await _load_user_group_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=201,
        content=_scim_user_resource(
            user,
            base_url=base_url,
            tenant_id=ctx.tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


@router.get("/Users/{user_id}")
async def get_user(
    request: Request,
    user_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc
    user = (
        await db.execute(
            select(User).where(User.tenant_id == ctx.tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise ScimError(404, "Resource not found")
    base_url = str(request.base_url).rstrip("/")
    group_map = await _load_user_group_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_user_resource(
            user,
            base_url=base_url,
            tenant_id=ctx.tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


@router.put("/Users/{user_id}")
async def put_user(
    request: Request,
    user_id: str,
    body: ScimUserPut,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    user = (
        await db.execute(
            select(User).where(User.tenant_id == ctx.tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise ScimError(404, "Resource not found")

    user.email = str(body.userName)
    user.is_active = bool(body.active)
    await _apply_scim_group_mappings(
        db,
        tenant_id=ctx.tenant_id,
        user=user,
        groups=body.groups,
        for_create=False,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "User already exists", scim_type="uniqueness") from exc

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_USER_UPDATED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={
            "email": str(user.email),
            "active": bool(user.is_active),
            "role": str(getattr(user, "role", "")),
            "persona": str(getattr(user, "persona", ""))
            if getattr(user, "persona", None)
            else None,
            "groups_provided": body.groups is not None,
            "groups_count": len(body.groups or []),
        },
        request_method="SCIM",
        request_path=f"/scim/v2/Users/{user.id}",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    group_map = await _load_user_group_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_user_resource(
            user,
            base_url=base_url,
            tenant_id=ctx.tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


def _apply_patch_operation(user: User, operation: ScimPatchOperation) -> None:
    op = operation.op.lower().strip()
    path = (operation.path or "").strip()
    value = operation.value

    if op not in {"add", "replace", "remove"}:
        raise ScimError(400, "Unsupported patch op", scim_type="invalidValue")

    # Minimal supported paths: active, userName
    if not path:
        # Some IdPs send no path and a dict value; we keep it strict for now.
        raise ScimError(400, "Patch path is required", scim_type="invalidPath")

    path_norm = path.strip().lower()
    if path_norm == "active":
        if op == "remove":
            user.is_active = False
            return
        if not isinstance(value, bool):
            raise ScimError(400, "active must be boolean", scim_type="invalidValue")
        user.is_active = bool(value)
        return

    if path_norm == "username":
        if op == "remove":
            raise ScimError(400, "userName cannot be removed", scim_type="invalidValue")
        if not isinstance(value, str) or "@" not in value:
            raise ScimError(400, "userName must be an email", scim_type="invalidValue")
        user.email = value.strip()
        return

    raise ScimError(400, "Unsupported patch path", scim_type="invalidPath")


@router.patch("/Users/{user_id}")
async def patch_user(
    request: Request,
    user_id: str,
    body: ScimPatchRequest,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    user = (
        await db.execute(
            select(User).where(User.tenant_id == ctx.tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise ScimError(404, "Resource not found")

    for operation in body.Operations:
        path_norm = (operation.path or "").strip().lower()
        if path_norm == "groups":
            op = operation.op.lower().strip()
            existing_dicts = (
                await _load_user_group_refs_map(
                    db,
                    tenant_id=ctx.tenant_id,
                    user_ids=[user.id],
                )
            ).get(user.id, [])
            existing_refs = [
                ScimGroupRef.model_validate(item)
                for item in existing_dicts
                if isinstance(item, dict)
            ]

            if op == "remove":
                refs: list[ScimGroupRef] = []
            elif op in {"replace", "add"}:
                if not isinstance(operation.value, list):
                    raise ScimError(
                        400,
                        "groups patch value must be a list",
                        scim_type="invalidValue",
                    )
                new_refs = [
                    ScimGroupRef.model_validate(item)
                    for item in operation.value
                    if isinstance(item, dict)
                ]
                refs = (existing_refs + new_refs) if op == "add" else new_refs
            else:
                raise ScimError(
                    400, "Unsupported patch op for groups", scim_type="invalidValue"
                )

            await _apply_scim_group_mappings(
                db,
                tenant_id=ctx.tenant_id,
                user=user,
                groups=refs,
                for_create=False,
            )
            continue

        _apply_patch_operation(user, operation)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "User already exists", scim_type="uniqueness") from exc

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_USER_UPDATED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": str(user.email), "active": bool(user.is_active)},
        request_method="SCIM",
        request_path=f"/scim/v2/Users/{user.id}",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    group_map = await _load_user_group_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_user_resource(
            user,
            base_url=base_url,
            tenant_id=ctx.tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


@router.delete("/Users/{user_id}")
async def delete_user(
    user_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc
    user = (
        await db.execute(
            select(User).where(User.tenant_id == ctx.tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise ScimError(404, "Resource not found")

    user.is_active = False
    await db.commit()

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_USER_DEPROVISIONED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": str(user.email), "active": bool(user.is_active)},
        request_method="SCIM",
        request_path=f"/scim/v2/Users/{user.id}",
    )
    await db.commit()

    return JSONResponse(status_code=204, content={})


@router.get("/Groups")
async def list_groups(
    request: Request,
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> ScimListResponse:
    if startIndex < 1:
        raise ScimError(400, "startIndex must be >= 1", scim_type="invalidValue")
    if count < 0 or count > 200:
        raise ScimError(
            400, "count must be between 0 and 200", scim_type="invalidValue"
        )

    stmt = (
        select(ScimGroup)
        .where(ScimGroup.tenant_id == ctx.tenant_id)
        .order_by(ScimGroup.display_name_norm.asc())
    )
    parsed_filter = _parse_group_filter(filter or "")
    if filter and parsed_filter is None:
        raise ScimError(400, "Unsupported filter expression", scim_type="invalidFilter")
    if parsed_filter:
        attr, value = parsed_filter
        if attr.lower() == "displayname":
            stmt = stmt.where(
                ScimGroup.display_name_norm == _normalize_scim_group(value)
            )
        elif attr.lower() == "externalid":
            stmt = stmt.where(
                ScimGroup.external_id_norm == (_normalize_scim_group(value) or None)
            )

    result = await db.execute(stmt)
    groups = list(result.scalars().all())
    total = len(groups)
    start = startIndex - 1
    end = start + count if count else start
    page = groups[start:end]

    base_url = str(request.base_url).rstrip("/")
    member_map = await _load_group_member_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        group_ids=[item.id for item in page],
    )
    resources = [
        _scim_group_resource(
            item,
            base_url=base_url,
            members=member_map.get(item.id, []),
        )
        for item in page
    ]
    return ScimListResponse(
        totalResults=total,
        startIndex=startIndex,
        itemsPerPage=len(page),
        Resources=resources,
    )


@router.post("/Groups")
async def create_group(
    request: Request,
    body: ScimGroupCreate,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    display = str(body.displayName or "").strip()
    if not display:
        raise ScimError(400, "displayName is required", scim_type="invalidValue")
    external_id = str(body.externalId).strip() if body.externalId else None
    external_norm = _normalize_scim_group(external_id or "") or None

    group = ScimGroup(
        id=uuid4(),
        tenant_id=ctx.tenant_id,
        display_name=display,
        display_name_norm=_normalize_scim_group(display),
        external_id=external_id,
        external_id_norm=external_norm,
    )
    db.add(group)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "Group already exists", scim_type="uniqueness") from exc

    member_user_ids: set[UUID] = set()
    missing_member_count = 0
    if body.members is not None:
        candidate_ids = {
            _parse_uuid(ref.value)
            for ref in body.members
            if _parse_uuid(ref.value) is not None
        }
        member_user_ids = await _resolve_member_user_ids(
            db, tenant_id=ctx.tenant_id, members=body.members
        )
        missing_member_count = len(candidate_ids) - len(member_user_ids)
        impacted = await _set_group_memberships(
            db,
            tenant_id=ctx.tenant_id,
            group_id=group.id,
            member_user_ids=member_user_ids,
        )
        await _recompute_entitlements_for_users(
            db, tenant_id=ctx.tenant_id, user_ids=impacted
        )

    await db.commit()

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_GROUP_CREATED,
        actor_id=None,
        resource_type="scim_group",
        resource_id=str(group.id),
        details={
            "display_name": display,
            "external_id_provided": bool(external_id),
            "members_provided": body.members is not None,
            "members_count": len(member_user_ids),
            "members_missing_count": missing_member_count,
        },
        request_method="SCIM",
        request_path="/scim/v2/Groups",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    member_map = await _load_group_member_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=201,
        content=_scim_group_resource(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


@router.get("/Groups/{group_id}")
async def get_group(
    request: Request,
    group_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(group_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == ctx.tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise ScimError(404, "Resource not found")

    base_url = str(request.base_url).rstrip("/")
    member_map = await _load_group_member_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_group_resource(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


@router.put("/Groups/{group_id}")
async def put_group(
    request: Request,
    group_id: str,
    body: ScimGroupPut,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(group_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == ctx.tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise ScimError(404, "Resource not found")

    display = str(body.displayName or "").strip()
    if not display:
        raise ScimError(400, "displayName is required", scim_type="invalidValue")

    group.display_name = display
    group.display_name_norm = _normalize_scim_group(display)

    external_id = str(body.externalId).strip() if body.externalId else None
    group.external_id = external_id
    group.external_id_norm = _normalize_scim_group(external_id or "") or None

    member_user_ids: set[UUID] = set()
    missing_member_count = 0
    impacted: set[UUID] = set()
    if body.members is not None:
        candidate_ids = {
            _parse_uuid(ref.value)
            for ref in body.members
            if _parse_uuid(ref.value) is not None
        }
        member_user_ids = await _resolve_member_user_ids(
            db, tenant_id=ctx.tenant_id, members=body.members
        )
        missing_member_count = len(candidate_ids) - len(member_user_ids)
        impacted = await _set_group_memberships(
            db,
            tenant_id=ctx.tenant_id,
            group_id=group.id,
            member_user_ids=member_user_ids,
        )
        await _recompute_entitlements_for_users(
            db, tenant_id=ctx.tenant_id, user_ids=impacted
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "Group already exists", scim_type="uniqueness") from exc

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_GROUP_UPDATED,
        actor_id=None,
        resource_type="scim_group",
        resource_id=str(group.id),
        details={
            "display_name": display,
            "external_id_provided": bool(external_id),
            "members_provided": body.members is not None,
            "members_count": len(member_user_ids),
            "members_missing_count": missing_member_count,
            "members_impacted_count": len(impacted),
        },
        request_method="SCIM",
        request_path=f"/scim/v2/Groups/{group.id}",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    member_map = await _load_group_member_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_group_resource(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


def _parse_member_filter_from_path(path: str) -> UUID | None:
    """
    Support Okta/Azure-style member remove path:
      members[value eq "uuid"]
    """
    path = (path or "").strip()
    m = re.match(r'(?i)^members\[value\s+eq\s+"([^"]+)"\]\s*$', path)
    if not m:
        return None
    return _parse_uuid(m.group(1).strip())


@router.patch("/Groups/{group_id}")
async def patch_group(
    request: Request,
    group_id: str,
    body: ScimPatchRequest,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(group_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == ctx.tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise ScimError(404, "Resource not found")

    member_action = False
    impacted_user_ids: set[UUID] = set()

    for operation in body.Operations:
        op = operation.op.lower().strip()
        path = (operation.path or "").strip()
        value = operation.value

        if op not in {"add", "replace", "remove"}:
            raise ScimError(400, "Unsupported patch op", scim_type="invalidValue")

        if not path:
            if op in {"add", "replace"} and isinstance(value, dict):
                if "displayName" in value:
                    name_val = str(value.get("displayName") or "").strip()
                    if not name_val:
                        raise ScimError(
                            400, "displayName is required", scim_type="invalidValue"
                        )
                    group.display_name = name_val
                    group.display_name_norm = _normalize_scim_group(name_val)
                if "externalId" in value:
                    ext_val = str(value.get("externalId") or "").strip() or None
                    group.external_id = ext_val
                    group.external_id_norm = (
                        _normalize_scim_group(ext_val or "") or None
                    )
                if "members" in value:
                    member_action = True
                    member_refs = value.get("members")
                    if not isinstance(member_refs, list):
                        raise ScimError(
                            400, "members must be a list", scim_type="invalidValue"
                        )
                    parsed_refs = [
                        ScimMemberRef.model_validate(item)
                        for item in member_refs
                        if isinstance(item, dict)
                    ]
                    member_user_ids = await _resolve_member_user_ids(
                        db, tenant_id=ctx.tenant_id, members=parsed_refs
                    )
                    impacted_user_ids |= await _set_group_memberships(
                        db,
                        tenant_id=ctx.tenant_id,
                        group_id=group.id,
                        member_user_ids=member_user_ids,
                    )
                continue
            raise ScimError(400, "Patch path is required", scim_type="invalidPath")

        path_norm = path.lower()
        if path_norm == "displayname":
            if op == "remove":
                raise ScimError(
                    400, "displayName cannot be removed", scim_type="invalidValue"
                )
            if not isinstance(value, str):
                raise ScimError(
                    400, "displayName must be string", scim_type="invalidValue"
                )
            name_val = value.strip()
            if not name_val:
                raise ScimError(
                    400, "displayName is required", scim_type="invalidValue"
                )
            group.display_name = name_val
            group.display_name_norm = _normalize_scim_group(name_val)
            continue

        if path_norm == "externalid":
            if op == "remove":
                group.external_id = None
                group.external_id_norm = None
                continue
            if not isinstance(value, str):
                raise ScimError(
                    400, "externalId must be string", scim_type="invalidValue"
                )
            ext_val = value.strip() or None
            group.external_id = ext_val
            group.external_id_norm = _normalize_scim_group(ext_val or "") or None
            continue

        if path_norm == "members" or path_norm.startswith("members["):
            member_action = True

            existing = await _load_group_member_user_ids(
                db, tenant_id=ctx.tenant_id, group_id=group.id
            )

            remove_from_path = (
                _parse_member_filter_from_path(path)
                if path_norm.startswith("members[")
                else None
            )

            if op == "replace":
                if not isinstance(value, list):
                    raise ScimError(
                        400,
                        "members patch value must be a list",
                        scim_type="invalidValue",
                    )
                parsed_refs = [
                    ScimMemberRef.model_validate(item)
                    for item in value
                    if isinstance(item, dict)
                ]
                member_user_ids = await _resolve_member_user_ids(
                    db, tenant_id=ctx.tenant_id, members=parsed_refs
                )
                impacted_user_ids |= await _set_group_memberships(
                    db,
                    tenant_id=ctx.tenant_id,
                    group_id=group.id,
                    member_user_ids=member_user_ids,
                )
                continue

            if op == "add":
                if isinstance(value, dict):
                    value_list = [value]
                elif isinstance(value, list):
                    value_list = value
                else:
                    raise ScimError(
                        400,
                        "members add value must be list or object",
                        scim_type="invalidValue",
                    )
                parsed_refs = [
                    ScimMemberRef.model_validate(item)
                    for item in value_list
                    if isinstance(item, dict)
                ]
                to_add = await _resolve_member_user_ids(
                    db, tenant_id=ctx.tenant_id, members=parsed_refs
                )
                impacted_user_ids |= await _set_group_memberships(
                    db,
                    tenant_id=ctx.tenant_id,
                    group_id=group.id,
                    member_user_ids=(existing | to_add),
                )
                continue

            if op == "remove":
                if remove_from_path is not None:
                    to_remove = {remove_from_path}
                elif isinstance(value, dict):
                    to_remove = await _resolve_member_user_ids(
                        db,
                        tenant_id=ctx.tenant_id,
                        members=[ScimMemberRef.model_validate(value)],
                    )
                elif isinstance(value, list):
                    parsed_refs = [
                        ScimMemberRef.model_validate(item)
                        for item in value
                        if isinstance(item, dict)
                    ]
                    to_remove = await _resolve_member_user_ids(
                        db, tenant_id=ctx.tenant_id, members=parsed_refs
                    )
                elif value is None:
                    to_remove = set()
                else:
                    raise ScimError(
                        400,
                        "members remove value must be list or object",
                        scim_type="invalidValue",
                    )

                impacted_user_ids |= await _set_group_memberships(
                    db,
                    tenant_id=ctx.tenant_id,
                    group_id=group.id,
                    member_user_ids=(existing - to_remove),
                )
                continue

        raise ScimError(400, "Unsupported patch path", scim_type="invalidPath")

    if member_action:
        await _recompute_entitlements_for_users(
            db, tenant_id=ctx.tenant_id, user_ids=impacted_user_ids
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ScimError(409, "Group already exists", scim_type="uniqueness") from exc

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_GROUP_UPDATED,
        actor_id=None,
        resource_type="scim_group",
        resource_id=str(group.id),
        details={
            "display_name": str(group.display_name),
            "external_id_provided": bool(getattr(group, "external_id", None)),
            "members_impacted_count": len(impacted_user_ids),
        },
        request_method="SCIM",
        request_path=f"/scim/v2/Groups/{group.id}",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    member_map = await _load_group_member_refs_map(
        db,
        tenant_id=ctx.tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=200,
        content=_scim_group_resource(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


@router.delete("/Groups/{group_id}")
async def delete_group(
    group_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    try:
        parsed_id = UUID(group_id)
    except ValueError as exc:
        raise ScimError(404, "Resource not found") from exc

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == ctx.tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise ScimError(404, "Resource not found")

    impacted_user_ids = await _load_group_member_user_ids(
        db, tenant_id=ctx.tenant_id, group_id=group.id
    )
    await db.execute(
        delete(ScimGroup).where(
            ScimGroup.tenant_id == ctx.tenant_id,
            ScimGroup.id == group.id,
        )
    )
    await _recompute_entitlements_for_users(
        db, tenant_id=ctx.tenant_id, user_ids=impacted_user_ids
    )
    await db.commit()

    audit = AuditLogger(db, ctx.tenant_id)
    await audit.log(
        event_type=AuditEventType.SCIM_GROUP_DELETED,
        actor_id=None,
        resource_type="scim_group",
        resource_id=str(group.id),
        details={
            "display_name": str(getattr(group, "display_name", "") or ""),
            "members_impacted_count": len(impacted_user_ids),
        },
        request_method="SCIM",
        request_path=f"/scim/v2/Groups/{group.id}",
    )
    await db.commit()

    return JSONResponse(status_code=204, content={})
