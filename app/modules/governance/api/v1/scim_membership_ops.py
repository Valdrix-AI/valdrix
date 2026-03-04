from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import User, UserPersona, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.api.v1.scim_models import ScimGroupRef, ScimMemberRef


async def load_user_group_refs_map(
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


async def load_group_member_refs_map(
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


async def resolve_groups_from_refs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    groups: list[ScimGroupRef],
    get_or_create_scim_group_fn: Callable[..., Awaitable[ScimGroup]],
    parse_uuid_fn: Callable[[str], UUID | None],
) -> tuple[set[UUID], set[str]]:
    group_ids: set[UUID] = set()
    group_names_norm: set[str] = set()

    group: ScimGroup | None = None
    for ref in groups:
        display = str(ref.display or "").strip()
        raw_value = str(ref.value or "").strip()

        if not display and not raw_value:
            continue

        if display:
            group = await get_or_create_scim_group_fn(
                db, tenant_id=tenant_id, display_name=display
            )
        else:
            parsed = parse_uuid_fn(raw_value)
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
                    group = await get_or_create_scim_group_fn(
                        db, tenant_id=tenant_id, display_name=raw_value
                    )
            else:
                group = await get_or_create_scim_group_fn(
                    db, tenant_id=tenant_id, display_name=raw_value
                )

        group_ids.add(group.id)
        group_names_norm.add(str(getattr(group, "display_name_norm", "") or ""))

    return group_ids, group_names_norm


async def resolve_member_user_ids(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    members: list[Any],
    parse_uuid_fn: Callable[[str], UUID | None],
) -> set[UUID]:
    candidate_ids: set[UUID] = set()
    for ref in members:
        parsed = parse_uuid_fn(str(getattr(ref, "value", "") or ""))
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


async def load_group_member_user_ids(
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


async def set_user_group_memberships(
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


async def set_group_memberships(
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


async def load_scim_group_mappings(
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


def resolve_entitlements_from_groups(
    group_names: set[str],
    mappings: list[dict[str, Any]],
    *,
    normalize_scim_group_fn: Callable[[str], str],
) -> tuple[str | None, str | None]:
    desired_role: str | None = None
    desired_persona: str | None = None

    for mapping in mappings:
        group = normalize_scim_group_fn(str(mapping.get("group", "")))
        if not group or group not in group_names:
            continue

        role = normalize_scim_group_fn(str(mapping.get("role", "")))
        if role == UserRole.ADMIN.value:
            desired_role = UserRole.ADMIN.value
        elif desired_role is None and role == UserRole.MEMBER.value:
            desired_role = UserRole.MEMBER.value

        persona = normalize_scim_group_fn(str(mapping.get("persona", "")))
        if desired_persona is None and persona in {
            UserPersona.ENGINEERING.value,
            UserPersona.FINANCE.value,
            UserPersona.PLATFORM.value,
            UserPersona.LEADERSHIP.value,
        }:
            desired_persona = persona

    return desired_role, desired_persona


async def load_user_group_names_from_memberships(
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


async def recompute_entitlements_for_users(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_ids: set[UUID],
    load_scim_group_mappings_fn: Callable[
        [AsyncSession, UUID], Awaitable[list[dict[str, Any]]]
    ],
    load_user_group_names_from_memberships_fn: Callable[..., Awaitable[set[str]]],
    resolve_entitlements_from_groups_fn: Callable[
        [set[str], list[dict[str, Any]]], tuple[str | None, str | None]
    ],
    normalize_scim_group_fn: Callable[[str], str],
) -> None:
    if not user_ids:
        return

    mappings = await load_scim_group_mappings_fn(db, tenant_id)

    for uid in sorted(user_ids, key=lambda x: str(x)):
        user = (
            await db.execute(
                select(User).where(User.tenant_id == tenant_id, User.id == uid)
            )
        ).scalar_one_or_none()
        if not user:
            continue
        current_role = normalize_scim_group_fn(str(getattr(user, "role", "")))
        if current_role == UserRole.OWNER.value:
            continue

        group_names = await load_user_group_names_from_memberships_fn(
            db, tenant_id=tenant_id, user_id=uid
        )
        desired_role, desired_persona = resolve_entitlements_from_groups_fn(
            group_names, mappings
        )

        user.role = desired_role or UserRole.MEMBER.value
        if desired_persona:
            user.persona = desired_persona


async def apply_scim_group_mappings(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user: User,
    groups: list[ScimGroupRef] | None,
    for_create: bool,
    resolve_groups_from_refs_fn: Callable[..., Awaitable[tuple[set[UUID], set[str]]]],
    set_user_group_memberships_fn: Callable[..., Awaitable[None]],
    load_scim_group_mappings_fn: Callable[
        [AsyncSession, UUID], Awaitable[list[dict[str, Any]]]
    ],
    resolve_entitlements_from_groups_fn: Callable[
        [set[str], list[dict[str, Any]]], tuple[str | None, str | None]
    ],
    normalize_scim_group_fn: Callable[[str], str],
) -> None:
    current_role = normalize_scim_group_fn(str(getattr(user, "role", "")))
    if current_role == UserRole.OWNER.value:
        return

    if groups is None:
        if for_create:
            user.role = UserRole.MEMBER.value
            user.persona = (
                getattr(user, "persona", None) or UserPersona.ENGINEERING.value
            )
        return

    group_ids, group_names = await resolve_groups_from_refs_fn(
        db, tenant_id=tenant_id, groups=groups
    )
    await set_user_group_memberships_fn(
        db, tenant_id=tenant_id, user_id=user.id, group_ids=group_ids
    )

    mappings = await load_scim_group_mappings_fn(db, tenant_id)
    desired_role, desired_persona = resolve_entitlements_from_groups_fn(
        group_names, mappings
    )

    user.role = desired_role or UserRole.MEMBER.value

    if desired_persona:
        user.persona = desired_persona
    elif for_create and not getattr(user, "persona", None):
        user.persona = UserPersona.ENGINEERING.value


async def apply_group_patch_operations(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    group: ScimGroup,
    operations: list[Any],
    normalize_scim_group_fn: Callable[[str], str],
    parse_member_filter_from_path_fn: Callable[[str], UUID | None],
    resolve_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    set_group_memberships_fn: Callable[..., Awaitable[set[UUID]]],
    load_group_member_user_ids_fn: Callable[..., Awaitable[set[UUID]]],
    scim_error_factory: Callable[[int, str, str | None], Exception],
) -> tuple[bool, set[UUID]]:
    member_action = False
    impacted_user_ids: set[UUID] = set()

    for operation in operations:
        op = str(getattr(operation, "op", "")).lower().strip()
        path = str(getattr(operation, "path", "") or "").strip()
        value = getattr(operation, "value", None)

        if op not in {"add", "replace", "remove"}:
            raise scim_error_factory(400, "Unsupported patch op", "invalidValue")

        if not path:
            if op in {"add", "replace"} and isinstance(value, dict):
                if "displayName" in value:
                    name_val = str(value.get("displayName") or "").strip()
                    if not name_val:
                        raise scim_error_factory(
                            400, "displayName is required", "invalidValue"
                        )
                    group.display_name = name_val
                    group.display_name_norm = normalize_scim_group_fn(name_val)
                if "externalId" in value:
                    ext_val = str(value.get("externalId") or "").strip() or None
                    group.external_id = ext_val
                    group.external_id_norm = (
                        normalize_scim_group_fn(ext_val or "") or None
                    )
                if "members" in value:
                    member_action = True
                    member_refs = value.get("members")
                    if not isinstance(member_refs, list):
                        raise scim_error_factory(
                            400, "members must be a list", "invalidValue"
                        )
                    parsed_refs = [
                        ScimMemberRef.model_validate(item)
                        for item in member_refs
                        if isinstance(item, dict)
                    ]
                    member_user_ids = await resolve_member_user_ids_fn(
                        db, tenant_id=tenant_id, members=parsed_refs
                    )
                    impacted_user_ids |= await set_group_memberships_fn(
                        db,
                        tenant_id=tenant_id,
                        group_id=group.id,
                        member_user_ids=member_user_ids,
                    )
                continue
            raise scim_error_factory(400, "Patch path is required", "invalidPath")

        path_norm = path.lower()
        if path_norm == "displayname":
            if op == "remove":
                raise scim_error_factory(
                    400, "displayName cannot be removed", "invalidValue"
                )
            if not isinstance(value, str):
                raise scim_error_factory(
                    400, "displayName must be string", "invalidValue"
                )
            name_val = value.strip()
            if not name_val:
                raise scim_error_factory(
                    400, "displayName is required", "invalidValue"
                )
            group.display_name = name_val
            group.display_name_norm = normalize_scim_group_fn(name_val)
            continue

        if path_norm == "externalid":
            if op == "remove":
                group.external_id = None
                group.external_id_norm = None
                continue
            if not isinstance(value, str):
                raise scim_error_factory(400, "externalId must be string", "invalidValue")
            ext_val = value.strip() or None
            group.external_id = ext_val
            group.external_id_norm = normalize_scim_group_fn(ext_val or "") or None
            continue

        if path_norm == "members" or path_norm.startswith("members["):
            member_action = True

            existing = await load_group_member_user_ids_fn(
                db, tenant_id=tenant_id, group_id=group.id
            )
            remove_from_path = (
                parse_member_filter_from_path_fn(path)
                if path_norm.startswith("members[")
                else None
            )

            if op == "replace":
                if not isinstance(value, list):
                    raise scim_error_factory(
                        400, "members patch value must be a list", "invalidValue"
                    )
                parsed_refs = [
                    ScimMemberRef.model_validate(item)
                    for item in value
                    if isinstance(item, dict)
                ]
                member_user_ids = await resolve_member_user_ids_fn(
                    db, tenant_id=tenant_id, members=parsed_refs
                )
                impacted_user_ids |= await set_group_memberships_fn(
                    db,
                    tenant_id=tenant_id,
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
                    raise scim_error_factory(
                        400, "members add value must be list or object", "invalidValue"
                    )
                parsed_refs = [
                    ScimMemberRef.model_validate(item)
                    for item in value_list
                    if isinstance(item, dict)
                ]
                to_add = await resolve_member_user_ids_fn(
                    db, tenant_id=tenant_id, members=parsed_refs
                )
                impacted_user_ids |= await set_group_memberships_fn(
                    db,
                    tenant_id=tenant_id,
                    group_id=group.id,
                    member_user_ids=(existing | to_add),
                )
                continue

            if op == "remove":
                if remove_from_path is not None:
                    to_remove = {remove_from_path}
                elif isinstance(value, dict):
                    to_remove = await resolve_member_user_ids_fn(
                        db,
                        tenant_id=tenant_id,
                        members=[ScimMemberRef.model_validate(value)],
                    )
                elif isinstance(value, list):
                    parsed_refs = [
                        ScimMemberRef.model_validate(item)
                        for item in value
                        if isinstance(item, dict)
                    ]
                    to_remove = await resolve_member_user_ids_fn(
                        db, tenant_id=tenant_id, members=parsed_refs
                    )
                elif value is None:
                    to_remove = set()
                else:
                    raise scim_error_factory(
                        400,
                        "members remove value must be list or object",
                        "invalidValue",
                    )

                impacted_user_ids |= await set_group_memberships_fn(
                    db,
                    tenant_id=tenant_id,
                    group_id=group.id,
                    member_user_ids=(existing - to_remove),
                )
                continue

        raise scim_error_factory(400, "Unsupported patch path", "invalidPath")

    return member_action, impacted_user_ids
