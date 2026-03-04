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

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, User
from app.models.scim_group import ScimGroup
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.modules.governance.api.v1.scim_group_route_ops import (
    create_group_route as _create_group_route_impl,
    delete_group_route as _delete_group_route_impl,
    list_groups_route as _list_groups_route_impl,
    patch_group_route as _patch_group_route_impl,
    put_group_route as _put_group_route_impl,
)
from app.shared.core.pricing import FeatureFlag, is_feature_enabled, normalize_tier
from app.shared.core.security import generate_secret_blind_index
from app.shared.db import session as db_session
from app.modules.governance.api.v1.scim_models import (
    ScimGroupCreate,
    ScimGroupPut,
    ScimGroupRef,
    ScimListResponse,
    ScimMemberRef,
    ScimPatchOperation,
    ScimPatchRequest,
    ScimUserCreate,
    ScimUserPut,
)
from app.modules.governance.api.v1.scim_schemas import (
    SCIM_ERROR_SCHEMA,
    SCIM_GROUP_SCHEMA,
    SCIM_LIST_SCHEMA,
    SCIM_USER_SCHEMA,
    resource_types_response,
    scim_group_schema_resource as _scim_group_schema_resource,
    scim_user_schema_resource as _scim_user_schema_resource,
    service_provider_config,
)
from app.modules.governance.api.v1.scim_utils import (
    normalize_scim_group as _normalize_scim_group,
    parse_group_filter as _parse_group_filter,
    parse_member_filter_from_path as _parse_member_filter_from_path,
    parse_user_filter as _parse_user_filter,
    parse_uuid as _parse_uuid,
)
from app.modules.governance.api.v1.scim_membership_ops import (
    apply_group_patch_operations as _apply_group_patch_operations_impl,
    apply_scim_group_mappings as _apply_scim_group_mappings_impl,
    load_group_member_refs_map as _load_group_member_refs_map_impl,
    load_group_member_user_ids as _load_group_member_user_ids_impl,
    load_scim_group_mappings as _load_scim_group_mappings_impl,
    load_user_group_names_from_memberships as _load_user_group_names_from_memberships_impl,
    load_user_group_refs_map as _load_user_group_refs_map_impl,
    recompute_entitlements_for_users as _recompute_entitlements_for_users_impl,
    resolve_entitlements_from_groups as _resolve_entitlements_from_groups_impl,
    resolve_groups_from_refs as _resolve_groups_from_refs_impl,
    resolve_member_user_ids as _resolve_member_user_ids_impl,
    set_group_memberships as _set_group_memberships_impl,
    set_user_group_memberships as _set_user_group_memberships_impl,
)
from app.modules.governance.api.v1.scim_user_route_ops import (
    create_user_route as _create_user_route_impl,
    delete_user_route as _delete_user_route_impl,
    get_user_route as _get_user_route_impl,
    list_users_route as _list_users_route_impl,
    patch_user_route as _patch_user_route_impl,
    put_user_route as _put_user_route_impl,
)

logger = structlog.get_logger()
router = APIRouter(tags=["SCIM"])


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
        await db_session.mark_session_system_context(db)
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


_load_user_group_refs_map = _load_user_group_refs_map_impl
_load_group_member_refs_map = _load_group_member_refs_map_impl


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
    return await _resolve_groups_from_refs_impl(
        db,
        tenant_id=tenant_id,
        groups=groups,
        get_or_create_scim_group_fn=_get_or_create_scim_group,
        parse_uuid_fn=_parse_uuid,
    )


async def _resolve_member_user_ids(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    members: list[ScimMemberRef],
) -> set[UUID]:
    return await _resolve_member_user_ids_impl(
        db,
        tenant_id=tenant_id,
        members=members,
        parse_uuid_fn=_parse_uuid,
    )


_load_group_member_user_ids = _load_group_member_user_ids_impl
_set_user_group_memberships = _set_user_group_memberships_impl
_set_group_memberships = _set_group_memberships_impl
_load_scim_group_mappings = _load_scim_group_mappings_impl


def _resolve_entitlements_from_groups(
    group_names: set[str],
    mappings: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    return _resolve_entitlements_from_groups_impl(
        group_names,
        mappings,
        normalize_scim_group_fn=_normalize_scim_group,
    )


_load_user_group_names_from_memberships = _load_user_group_names_from_memberships_impl


async def _recompute_entitlements_for_users(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: set[UUID],
) -> None:
    await _recompute_entitlements_for_users_impl(
        db,
        tenant_id=tenant_id,
        user_ids=user_ids,
        load_scim_group_mappings_fn=_load_scim_group_mappings,
        load_user_group_names_from_memberships_fn=_load_user_group_names_from_memberships,
        resolve_entitlements_from_groups_fn=_resolve_entitlements_from_groups,
        normalize_scim_group_fn=_normalize_scim_group,
    )


async def _apply_scim_group_mappings(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user: User,
    groups: list[ScimGroupRef] | None,
    for_create: bool,
) -> None:
    await _apply_scim_group_mappings_impl(
        db,
        tenant_id=tenant_id,
        user=user,
        groups=groups,
        for_create=for_create,
        resolve_groups_from_refs_fn=_resolve_groups_from_refs,
        set_user_group_memberships_fn=_set_user_group_memberships,
        load_scim_group_mappings_fn=_load_scim_group_mappings,
        resolve_entitlements_from_groups_fn=_resolve_entitlements_from_groups,
        normalize_scim_group_fn=_normalize_scim_group,
    )


def _make_scim_error(
    status_code: int, detail: str, scim_type: str | None = None
) -> ScimError:
    return ScimError(status_code, detail, scim_type=scim_type)


@router.get("/ServiceProviderConfig")
async def get_service_provider_config() -> dict[str, Any]:
    return service_provider_config()


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
    return resource_types_response()


@router.get("/Users")
async def list_users(
    request: Request,
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> ScimListResponse:
    return await _list_users_route_impl(
        request=request,
        start_index=startIndex,
        count=count,
        filter_expr=filter,
        tenant_id=ctx.tenant_id,
        db=db,
        parse_user_filter_fn=_parse_user_filter,
        load_user_group_refs_map_fn=_load_user_group_refs_map,
        scim_user_resource_fn=_scim_user_resource,
        scim_error_factory=_make_scim_error,
    )


@router.post("/Users")
async def create_user(
    request: Request,
    body: ScimUserCreate,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    return await _create_user_route_impl(
        request=request,
        body=body,
        tenant_id=ctx.tenant_id,
        db=db,
        apply_scim_group_mappings_fn=_apply_scim_group_mappings,
        load_user_group_refs_map_fn=_load_user_group_refs_map,
        scim_user_resource_fn=_scim_user_resource,
        scim_error_factory=_make_scim_error,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
    )


@router.get("/Users/{user_id}")
async def get_user(
    request: Request,
    user_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    return await _get_user_route_impl(
        request=request,
        user_id=user_id,
        tenant_id=ctx.tenant_id,
        db=db,
        load_user_group_refs_map_fn=_load_user_group_refs_map,
        scim_user_resource_fn=_scim_user_resource,
        scim_error_factory=_make_scim_error,
    )


@router.put("/Users/{user_id}")
async def put_user(
    request: Request,
    user_id: str,
    body: ScimUserPut,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    return await _put_user_route_impl(
        request=request,
        user_id=user_id,
        body=body,
        tenant_id=ctx.tenant_id,
        db=db,
        apply_scim_group_mappings_fn=_apply_scim_group_mappings,
        load_user_group_refs_map_fn=_load_user_group_refs_map,
        scim_user_resource_fn=_scim_user_resource,
        scim_error_factory=_make_scim_error,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
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
    return await _patch_user_route_impl(
        request=request,
        user_id=user_id,
        body=body,
        tenant_id=ctx.tenant_id,
        db=db,
        apply_patch_operation_fn=_apply_patch_operation,
        apply_scim_group_mappings_fn=_apply_scim_group_mappings,
        load_user_group_refs_map_fn=_load_user_group_refs_map,
        scim_user_resource_fn=_scim_user_resource,
        scim_group_ref_model=ScimGroupRef,
        scim_error_factory=_make_scim_error,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
    )


@router.delete("/Users/{user_id}")
async def delete_user(
    user_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    return await _delete_user_route_impl(
        user_id=user_id,
        tenant_id=ctx.tenant_id,
        db=db,
        scim_error_factory=_make_scim_error,
        audit_logger_cls=AuditLogger,
        audit_event_type=AuditEventType,
    )


@router.get("/Groups")
async def list_groups(
    request: Request,
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> ScimListResponse:
    base_url = str(request.base_url).rstrip("/")
    return await _list_groups_route_impl(
        db=db,
        tenant_id=ctx.tenant_id,
        start_index=startIndex,
        count=count,
        filter_expr=filter,
        base_url=base_url,
        parse_group_filter_fn=_parse_group_filter,
        normalize_scim_group_fn=_normalize_scim_group,
        load_group_member_refs_map_fn=_load_group_member_refs_map,
        scim_group_resource_fn=_scim_group_resource,
        scim_error_factory=_make_scim_error,
    )


@router.post("/Groups")
async def create_group(
    request: Request,
    body: ScimGroupCreate,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    return await _create_group_route_impl(
        db=db,
        tenant_id=ctx.tenant_id,
        body=body,
        base_url=base_url,
        parse_uuid_fn=_parse_uuid,
        normalize_scim_group_fn=_normalize_scim_group,
        resolve_member_user_ids_fn=_resolve_member_user_ids,
        set_group_memberships_fn=_set_group_memberships,
        recompute_entitlements_for_users_fn=_recompute_entitlements_for_users,
        load_group_member_refs_map_fn=_load_group_member_refs_map,
        scim_group_resource_fn=_scim_group_resource,
        scim_error_factory=_make_scim_error,
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
    base_url = str(request.base_url).rstrip("/")
    return await _put_group_route_impl(
        db=db,
        tenant_id=ctx.tenant_id,
        group_id=group_id,
        body=body,
        base_url=base_url,
        parse_uuid_fn=_parse_uuid,
        normalize_scim_group_fn=_normalize_scim_group,
        resolve_member_user_ids_fn=_resolve_member_user_ids,
        set_group_memberships_fn=_set_group_memberships,
        recompute_entitlements_for_users_fn=_recompute_entitlements_for_users,
        load_group_member_refs_map_fn=_load_group_member_refs_map,
        scim_group_resource_fn=_scim_group_resource,
        scim_error_factory=_make_scim_error,
    )


@router.patch("/Groups/{group_id}")
async def patch_group(
    request: Request,
    group_id: str,
    body: ScimPatchRequest,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    base_url = str(request.base_url).rstrip("/")
    return await _patch_group_route_impl(
        db=db,
        tenant_id=ctx.tenant_id,
        group_id=group_id,
        body=body,
        base_url=base_url,
        parse_uuid_fn=_parse_uuid,
        apply_group_patch_operations_fn=_apply_group_patch_operations_impl,
        normalize_scim_group_fn=_normalize_scim_group,
        parse_member_filter_from_path_fn=_parse_member_filter_from_path,
        resolve_member_user_ids_fn=_resolve_member_user_ids,
        set_group_memberships_fn=_set_group_memberships,
        load_group_member_user_ids_fn=_load_group_member_user_ids,
        recompute_entitlements_for_users_fn=_recompute_entitlements_for_users,
        load_group_member_refs_map_fn=_load_group_member_refs_map,
        scim_group_resource_fn=_scim_group_resource,
        scim_error_factory=_make_scim_error,
    )


@router.delete("/Groups/{group_id}")
async def delete_group(
    group_id: str,
    ctx: ScimContext = Depends(get_scim_context),
    db: AsyncSession = Depends(get_scim_db),
) -> JSONResponse:
    return await _delete_group_route_impl(
        db=db,
        tenant_id=ctx.tenant_id,
        group_id=group_id,
        parse_uuid_fn=_parse_uuid,
        load_group_member_user_ids_fn=_load_group_member_user_ids,
        recompute_entitlements_for_users_fn=_recompute_entitlements_for_users,
        scim_error_factory=_make_scim_error,
    )
