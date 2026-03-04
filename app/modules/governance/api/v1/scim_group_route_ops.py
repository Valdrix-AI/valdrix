from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scim_group import ScimGroup
from app.modules.governance.api.v1.scim_models import (
    ScimGroupCreate,
    ScimGroupPut,
    ScimListResponse,
    ScimPatchRequest,
)
from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger


async def list_groups_route(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    start_index: int,
    count: int,
    filter_expr: str | None,
    base_url: str,
    parse_group_filter_fn: Callable[[str], tuple[str, str] | None],
    normalize_scim_group_fn: Callable[[str], str],
    load_group_member_refs_map_fn: Callable[..., Awaitable[dict[UUID, list[dict[str, Any]]]]],
    scim_group_resource_fn: Callable[..., dict[str, Any]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> ScimListResponse:
    if start_index < 1:
        raise scim_error_factory(400, "startIndex must be >= 1", "invalidValue")
    if count < 0 or count > 200:
        raise scim_error_factory(400, "count must be between 0 and 200", "invalidValue")

    stmt = (
        select(ScimGroup)
        .where(ScimGroup.tenant_id == tenant_id)
        .order_by(ScimGroup.display_name_norm.asc())
    )
    parsed_filter = parse_group_filter_fn(filter_expr or "")
    if filter_expr and parsed_filter is None:
        raise scim_error_factory(400, "Unsupported filter expression", "invalidFilter")
    if parsed_filter:
        attr, value = parsed_filter
        if attr.lower() == "displayname":
            stmt = stmt.where(
                ScimGroup.display_name_norm == normalize_scim_group_fn(value)
            )
        elif attr.lower() == "externalid":
            stmt = stmt.where(
                ScimGroup.external_id_norm == (normalize_scim_group_fn(value) or None)
            )

    result = await db.execute(stmt)
    groups = list(result.scalars().all())
    total = len(groups)
    start = start_index - 1
    end = start + count if count else start
    page = groups[start:end]

    member_map = await load_group_member_refs_map_fn(
        db,
        tenant_id=tenant_id,
        group_ids=[item.id for item in page],
    )
    resources = [
        scim_group_resource_fn(
            item,
            base_url=base_url,
            members=member_map.get(item.id, []),
        )
        for item in page
    ]
    return ScimListResponse(
        totalResults=total,
        startIndex=start_index,
        itemsPerPage=len(page),
        Resources=resources,
    )


async def create_group_route(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    body: ScimGroupCreate,
    base_url: str,
    parse_uuid_fn: Callable[[str], UUID | None],
    normalize_scim_group_fn: Callable[[str], str],
    resolve_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    set_group_memberships_fn: Callable[..., Awaitable[set[UUID]]],
    recompute_entitlements_for_users_fn: Callable[..., Awaitable[None]],
    load_group_member_refs_map_fn: Callable[..., Awaitable[dict[UUID, list[dict[str, Any]]]]],
    scim_group_resource_fn: Callable[..., dict[str, Any]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> JSONResponse:
    display = str(body.displayName or "").strip()
    if not display:
        raise scim_error_factory(400, "displayName is required", "invalidValue")
    external_id = str(body.externalId).strip() if body.externalId else None
    external_norm = normalize_scim_group_fn(external_id or "") or None

    group = ScimGroup(
        id=uuid4(),
        tenant_id=tenant_id,
        display_name=display,
        display_name_norm=normalize_scim_group_fn(display),
        external_id=external_id,
        external_id_norm=external_norm,
    )
    db.add(group)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "Group already exists", "uniqueness") from exc

    member_user_ids: set[UUID] = set()
    missing_member_count = 0
    if body.members is not None:
        candidate_ids = {
            parsed
            for ref in body.members
            if (parsed := parse_uuid_fn(str(ref.value or ""))) is not None
        }
        member_user_ids = await resolve_member_user_ids_fn(
            db, tenant_id=tenant_id, members=body.members
        )
        missing_member_count = len(candidate_ids) - len(member_user_ids)
        impacted = await set_group_memberships_fn(
            db,
            tenant_id=tenant_id,
            group_id=group.id,
            member_user_ids=member_user_ids,
        )
        await recompute_entitlements_for_users_fn(
            db, tenant_id=tenant_id, user_ids=impacted
        )

    await db.commit()
    audit = AuditLogger(db, tenant_id)
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

    member_map = await load_group_member_refs_map_fn(
        db,
        tenant_id=tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=201,
        content=scim_group_resource_fn(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


async def put_group_route(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    group_id: str,
    body: ScimGroupPut,
    base_url: str,
    parse_uuid_fn: Callable[[str], UUID | None],
    normalize_scim_group_fn: Callable[[str], str],
    resolve_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    set_group_memberships_fn: Callable[..., Awaitable[set[UUID]]],
    recompute_entitlements_for_users_fn: Callable[..., Awaitable[None]],
    load_group_member_refs_map_fn: Callable[..., Awaitable[dict[UUID, list[dict[str, Any]]]]],
    scim_group_resource_fn: Callable[..., dict[str, Any]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> JSONResponse:
    parsed_id = parse_uuid_fn(group_id)
    if parsed_id is None:
        raise scim_error_factory(404, "Resource not found", None)

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise scim_error_factory(404, "Resource not found", None)

    display = str(body.displayName or "").strip()
    if not display:
        raise scim_error_factory(400, "displayName is required", "invalidValue")

    group.display_name = display
    group.display_name_norm = normalize_scim_group_fn(display)

    external_id = str(body.externalId).strip() if body.externalId else None
    group.external_id = external_id
    group.external_id_norm = normalize_scim_group_fn(external_id or "") or None

    member_user_ids: set[UUID] = set()
    missing_member_count = 0
    impacted: set[UUID] = set()
    with db.no_autoflush:
        if body.members is not None:
            candidate_ids = {
                parsed
                for ref in body.members
                if (parsed := parse_uuid_fn(str(ref.value or ""))) is not None
            }
            member_user_ids = await resolve_member_user_ids_fn(
                db, tenant_id=tenant_id, members=body.members
            )
            missing_member_count = len(candidate_ids) - len(member_user_ids)
            impacted = await set_group_memberships_fn(
                db,
                tenant_id=tenant_id,
                group_id=group.id,
                member_user_ids=member_user_ids,
            )
            await recompute_entitlements_for_users_fn(
                db, tenant_id=tenant_id, user_ids=impacted
            )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "Group already exists", "uniqueness") from exc

    audit = AuditLogger(db, tenant_id)
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

    member_map = await load_group_member_refs_map_fn(
        db,
        tenant_id=tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=200,
        content=scim_group_resource_fn(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


async def patch_group_route(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    group_id: str,
    body: ScimPatchRequest,
    base_url: str,
    parse_uuid_fn: Callable[[str], UUID | None],
    apply_group_patch_operations_fn: Callable[..., Awaitable[tuple[bool, set[UUID]]]],
    normalize_scim_group_fn: Callable[[str], str],
    parse_member_filter_from_path_fn: Callable[[str], UUID | None],
    resolve_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    set_group_memberships_fn: Callable[..., Awaitable[set[UUID]]],
    load_group_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    recompute_entitlements_for_users_fn: Callable[..., Awaitable[None]],
    load_group_member_refs_map_fn: Callable[..., Awaitable[dict[UUID, list[dict[str, Any]]]]],
    scim_group_resource_fn: Callable[..., dict[str, Any]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> JSONResponse:
    parsed_id = parse_uuid_fn(group_id)
    if parsed_id is None:
        raise scim_error_factory(404, "Resource not found", None)

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise scim_error_factory(404, "Resource not found", None)

    with db.no_autoflush:
        member_action, impacted_user_ids = await apply_group_patch_operations_fn(
            db=db,
            tenant_id=tenant_id,
            group=group,
            operations=body.Operations,
            normalize_scim_group_fn=normalize_scim_group_fn,
            parse_member_filter_from_path_fn=parse_member_filter_from_path_fn,
            resolve_member_user_ids_fn=resolve_member_user_ids_fn,
            set_group_memberships_fn=set_group_memberships_fn,
            load_group_member_user_ids_fn=load_group_member_user_ids_fn,
            scim_error_factory=scim_error_factory,
        )

    if member_action:
        await recompute_entitlements_for_users_fn(
            db, tenant_id=tenant_id, user_ids=impacted_user_ids
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "Group already exists", "uniqueness") from exc

    audit = AuditLogger(db, tenant_id)
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

    member_map = await load_group_member_refs_map_fn(
        db,
        tenant_id=tenant_id,
        group_ids=[group.id],
    )
    return JSONResponse(
        status_code=200,
        content=scim_group_resource_fn(
            group,
            base_url=base_url,
            members=member_map.get(group.id, []),
        ),
    )


async def delete_group_route(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    group_id: str,
    parse_uuid_fn: Callable[[str], UUID | None],
    load_group_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    recompute_entitlements_for_users_fn: Callable[..., Awaitable[None]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> JSONResponse:
    parsed_id = parse_uuid_fn(group_id)
    if parsed_id is None:
        raise scim_error_factory(404, "Resource not found", None)

    group = (
        await db.execute(
            select(ScimGroup).where(
                ScimGroup.tenant_id == tenant_id, ScimGroup.id == parsed_id
            )
        )
    ).scalar_one_or_none()
    if not group:
        raise scim_error_factory(404, "Resource not found", None)

    impacted_user_ids = await load_group_member_user_ids_fn(
        db, tenant_id=tenant_id, group_id=group.id
    )
    await db.execute(
        delete(ScimGroup).where(
            ScimGroup.tenant_id == tenant_id,
            ScimGroup.id == group.id,
        )
    )
    await recompute_entitlements_for_users_fn(
        db, tenant_id=tenant_id, user_ids=impacted_user_ids
    )
    await db.commit()

    audit = AuditLogger(db, tenant_id)
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
