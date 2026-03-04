from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import User, UserRole
from app.modules.governance.api.v1.scim_models import (
    ScimGroupRef,
    ScimListResponse,
    ScimPatchRequest,
    ScimUserCreate,
    ScimUserPut,
)


async def list_users_route(
    *,
    request: Request,
    start_index: int,
    count: int,
    filter_expr: str | None,
    tenant_id: UUID,
    db: AsyncSession,
    parse_user_filter_fn: Any,
    load_user_group_refs_map_fn: Any,
    scim_user_resource_fn: Any,
    scim_error_factory: Any,
) -> ScimListResponse:
    if start_index < 1:
        raise scim_error_factory(
            400,
            "startIndex must be >= 1",
            scim_type="invalidValue",
        )
    if count < 0 or count > 200:
        raise scim_error_factory(
            400,
            "count must be between 0 and 200",
            scim_type="invalidValue",
        )

    stmt = select(User).where(User.tenant_id == tenant_id)
    email_filter = parse_user_filter_fn(filter_expr or "")
    if filter_expr and email_filter is None:
        raise scim_error_factory(
            400,
            "Unsupported filter expression",
            scim_type="invalidFilter",
        )
    if email_filter:
        stmt = stmt.where(User.email == email_filter)

    result = await db.execute(stmt)
    users = list(result.scalars().all())
    total = len(users)
    start = start_index - 1
    end = start + count if count else start
    page = users[start:end]

    base_url = str(request.base_url).rstrip("/")
    group_map = await load_user_group_refs_map_fn(
        db,
        tenant_id=tenant_id,
        user_ids=[item.id for item in page],
    )
    resources = [
        scim_user_resource_fn(
            item,
            base_url=base_url,
            tenant_id=tenant_id,
            groups=group_map.get(item.id, []),
        )
        for item in page
    ]
    return ScimListResponse(
        totalResults=total,
        startIndex=start_index,
        itemsPerPage=len(page),
        Resources=resources,
    )


async def create_user_route(
    *,
    request: Request,
    body: ScimUserCreate,
    tenant_id: UUID,
    db: AsyncSession,
    apply_scim_group_mappings_fn: Any,
    load_user_group_refs_map_fn: Any,
    scim_user_resource_fn: Any,
    scim_error_factory: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
) -> JSONResponse:
    user = User(
        id=uuid4(),
        tenant_id=tenant_id,
        email=str(body.userName),
        role=UserRole.MEMBER.value,
        is_active=bool(body.active),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "User already exists", scim_type="uniqueness") from exc

    await apply_scim_group_mappings_fn(
        db,
        tenant_id=tenant_id,
        user=user,
        groups=body.groups,
        for_create=True,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "User already exists", scim_type="uniqueness") from exc

    audit = audit_logger_cls(db, tenant_id)
    await audit.log(
        event_type=audit_event_type.SCIM_USER_CREATED,
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
    group_map = await load_user_group_refs_map_fn(
        db,
        tenant_id=tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=201,
        content=scim_user_resource_fn(
            user,
            base_url=base_url,
            tenant_id=tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


async def get_user_route(
    *,
    request: Request,
    user_id: str,
    tenant_id: UUID,
    db: AsyncSession,
    load_user_group_refs_map_fn: Any,
    scim_user_resource_fn: Any,
    scim_error_factory: Any,
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise scim_error_factory(404, "Resource not found") from exc
    user = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise scim_error_factory(404, "Resource not found")

    base_url = str(request.base_url).rstrip("/")
    group_map = await load_user_group_refs_map_fn(
        db,
        tenant_id=tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=scim_user_resource_fn(
            user,
            base_url=base_url,
            tenant_id=tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


async def put_user_route(
    *,
    request: Request,
    user_id: str,
    body: ScimUserPut,
    tenant_id: UUID,
    db: AsyncSession,
    apply_scim_group_mappings_fn: Any,
    load_user_group_refs_map_fn: Any,
    scim_user_resource_fn: Any,
    scim_error_factory: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise scim_error_factory(404, "Resource not found") from exc

    user = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise scim_error_factory(404, "Resource not found")

    user.email = str(body.userName)
    user.is_active = bool(body.active)
    await apply_scim_group_mappings_fn(
        db,
        tenant_id=tenant_id,
        user=user,
        groups=body.groups,
        for_create=False,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "User already exists", scim_type="uniqueness") from exc

    audit = audit_logger_cls(db, tenant_id)
    await audit.log(
        event_type=audit_event_type.SCIM_USER_UPDATED,
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
    group_map = await load_user_group_refs_map_fn(
        db,
        tenant_id=tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=scim_user_resource_fn(
            user,
            base_url=base_url,
            tenant_id=tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


async def patch_user_route(
    *,
    request: Request,
    user_id: str,
    body: ScimPatchRequest,
    tenant_id: UUID,
    db: AsyncSession,
    apply_patch_operation_fn: Any,
    apply_scim_group_mappings_fn: Any,
    load_user_group_refs_map_fn: Any,
    scim_user_resource_fn: Any,
    scim_group_ref_model: Any,
    scim_error_factory: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise scim_error_factory(404, "Resource not found") from exc

    user = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise scim_error_factory(404, "Resource not found")

    for operation in body.Operations:
        path_norm = (operation.path or "").strip().lower()
        if path_norm == "groups":
            op = operation.op.lower().strip()
            existing_dicts = (
                await load_user_group_refs_map_fn(
                    db,
                    tenant_id=tenant_id,
                    user_ids=[user.id],
                )
            ).get(user.id, [])
            existing_refs = [
                scim_group_ref_model.model_validate(item)
                for item in existing_dicts
                if isinstance(item, dict)
            ]

            if op == "remove":
                refs: list[ScimGroupRef] = []
            elif op in {"replace", "add"}:
                if not isinstance(operation.value, list):
                    raise scim_error_factory(
                        400,
                        "groups patch value must be a list",
                        scim_type="invalidValue",
                    )
                new_refs = [
                    scim_group_ref_model.model_validate(item)
                    for item in operation.value
                    if isinstance(item, dict)
                ]
                refs = (existing_refs + new_refs) if op == "add" else new_refs
            else:
                raise scim_error_factory(
                    400,
                    "Unsupported patch op for groups",
                    scim_type="invalidValue",
                )

            await apply_scim_group_mappings_fn(
                db,
                tenant_id=tenant_id,
                user=user,
                groups=refs,
                for_create=False,
            )
            continue

        apply_patch_operation_fn(user, operation)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise scim_error_factory(409, "User already exists", scim_type="uniqueness") from exc

    audit = audit_logger_cls(db, tenant_id)
    await audit.log(
        event_type=audit_event_type.SCIM_USER_UPDATED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": str(user.email), "active": bool(user.is_active)},
        request_method="SCIM",
        request_path=f"/scim/v2/Users/{user.id}",
    )
    await db.commit()

    base_url = str(request.base_url).rstrip("/")
    group_map = await load_user_group_refs_map_fn(
        db,
        tenant_id=tenant_id,
        user_ids=[user.id],
    )
    return JSONResponse(
        status_code=200,
        content=scim_user_resource_fn(
            user,
            base_url=base_url,
            tenant_id=tenant_id,
            groups=group_map.get(user.id, []),
        ),
    )


async def delete_user_route(
    *,
    user_id: str,
    tenant_id: UUID,
    db: AsyncSession,
    scim_error_factory: Any,
    audit_logger_cls: Any,
    audit_event_type: Any,
) -> JSONResponse:
    try:
        parsed_id = UUID(user_id)
    except ValueError as exc:
        raise scim_error_factory(404, "Resource not found") from exc
    user = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == parsed_id)
        )
    ).scalar_one_or_none()
    if not user:
        raise scim_error_factory(404, "Resource not found")

    user.is_active = False
    await db.commit()

    audit = audit_logger_cls(db, tenant_id)
    await audit.log(
        event_type=audit_event_type.SCIM_USER_DEPROVISIONED,
        actor_id=None,
        resource_type="user",
        resource_id=str(user.id),
        details={"email": str(user.email), "active": bool(user.is_active)},
        request_method="SCIM",
        request_path=f"/scim/v2/Users/{user.id}",
    )
    await db.commit()
    return JSONResponse(status_code=204, content={})
