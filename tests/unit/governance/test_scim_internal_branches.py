from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import Request
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scim_group import ScimGroup, ScimGroupMember
from app.models.tenant import Tenant, User, UserPersona, UserRole
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.api.v1.scim import (
    ScimError,
    _apply_scim_group_mappings,
    _get_or_create_scim_group,
    _load_group_member_refs_map,
    _load_scim_group_mappings,
    _load_user_group_names_from_memberships,
    _load_user_group_refs_map,
    _recompute_entitlements_for_users,
    _resolve_groups_from_refs,
    _resolve_member_user_ids,
    _set_group_memberships,
    _set_user_group_memberships,
    get_scim_context,
)
from app.modules.governance.api.v1.scim_models import ScimGroupRef, ScimMemberRef


def _req_with_bearer(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


async def _seed_scim_tenant(
    db: AsyncSession,
    *,
    plan: str = "enterprise",
    scim_enabled: bool = True,
    mappings: list[dict[str, Any]] | None = None,
) -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    token = f"scim-token-{uuid.uuid4()}"
    db.add(Tenant(id=tenant_id, name=f"SCIM Internal {tenant_id}", plan=plan))
    db.add(
        TenantIdentitySettings(
            tenant_id=tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            scim_enabled=scim_enabled,
            scim_bearer_token=token,
            scim_last_rotated_at=datetime.now(timezone.utc),
            scim_group_mappings=mappings or [],
        )
    )
    await db.commit()
    return tenant_id, token


def _new_user(tenant_id: uuid.UUID, email: str, *, role: str = "member", persona: str = "engineering") -> User:
    return User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email=email,
        role=role,
        persona=persona,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_get_scim_context_rejects_empty_blind_index() -> None:
    request = _req_with_bearer("token-value")
    with patch(
        "app.modules.governance.api.v1.scim.generate_secret_blind_index", return_value=""
    ):
        with pytest.raises(ScimError, match="Invalid bearer token"):
            await get_scim_context(request)


@pytest.mark.asyncio
async def test_scim_service_metadata_and_not_found_schema(ac: AsyncClient) -> None:
    svc = await ac.get("/scim/v2/ServiceProviderConfig")
    assert svc.status_code == 200
    assert "patch" in svc.json()

    resource_types = await ac.get("/scim/v2/ResourceTypes")
    assert resource_types.status_code == 200
    assert resource_types.json().get("totalResults") == 2

    missing_schema = await ac.get("/scim/v2/Schemas/urn:ietf:params:scim:schemas:core:2.0:Foo")
    assert missing_schema.status_code == 404


@pytest.mark.asyncio
async def test_scim_user_uniqueness_delete_and_group_put_conflict_paths(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}

    first = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "dup@example.com", "active": True},
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    duplicate_create = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "dup@example.com", "active": True},
    )
    assert duplicate_create.status_code == 409

    second = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "other@example.com", "active": True},
    )
    assert second.status_code == 201
    second_id = second.json()["id"]

    put_conflict = await ac.put(
        f"/scim/v2/Users/{second_id}",
        headers=headers,
        json={"userName": "dup@example.com", "active": True},
    )
    assert put_conflict.status_code == 409

    patch_conflict = await ac.patch(
        f"/scim/v2/Users/{second_id}",
        headers=headers,
        json={"Operations": [{"op": "replace", "path": "userName", "value": "dup@example.com"}]},
    )
    assert patch_conflict.status_code == 409

    bad_delete = await ac.delete("/scim/v2/Users/not-a-uuid", headers=headers)
    assert bad_delete.status_code == 404
    missing_delete = await ac.delete(f"/scim/v2/Users/{uuid.uuid4()}", headers=headers)
    assert missing_delete.status_code == 404

    deleted = await ac.delete(f"/scim/v2/Users/{first_id}", headers=headers)
    assert deleted.status_code == 204

    g1 = await ac.post("/scim/v2/Groups", headers=headers, json={"displayName": "Team One"})
    g2 = await ac.post("/scim/v2/Groups", headers=headers, json={"displayName": "Team Two"})
    assert g1.status_code == 201
    assert g2.status_code == 201
    g1_id = g1.json()["id"]

    put_group_conflict = await ac.put(
        f"/scim/v2/Groups/{g1_id}",
        headers=headers,
        json={"displayName": "Team Two", "members": []},
    )
    assert put_group_conflict.status_code == 409


@pytest.mark.asyncio
async def test_scim_group_user_map_helpers_cover_empty_and_populated(db: AsyncSession) -> None:
    tenant_id, _ = await _seed_scim_tenant(db)
    u1 = _new_user(tenant_id, "u1@example.com")
    u2 = _new_user(tenant_id, "u2@example.com")
    group = ScimGroup(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        display_name="FinOps Admins",
        display_name_norm="finops admins",
        external_id=None,
        external_id_norm=None,
    )
    db.add_all([u1, u2, group])
    await db.flush()
    db.add(
        ScimGroupMember(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            group_id=group.id,
            user_id=u1.id,
        )
    )
    await db.commit()

    assert await _load_user_group_refs_map(db, tenant_id=tenant_id, user_ids=[]) == {}
    by_user = await _load_user_group_refs_map(
        db, tenant_id=tenant_id, user_ids=[u1.id, u2.id]
    )
    assert len(by_user[u1.id]) == 1
    assert by_user[u2.id] == []

    assert await _load_group_member_refs_map(db, tenant_id=tenant_id, group_ids=[]) == {}
    by_group = await _load_group_member_refs_map(db, tenant_id=tenant_id, group_ids=[group.id])
    assert len(by_group[group.id]) == 1
    assert by_group[group.id][0]["display"] == "u1@example.com"


@pytest.mark.asyncio
async def test_scim_group_resolution_and_membership_setters_cover_branches(
    db: AsyncSession,
) -> None:
    tenant_id, _ = await _seed_scim_tenant(db)
    u1 = _new_user(tenant_id, "a@example.com")
    u2 = _new_user(tenant_id, "b@example.com")
    u3 = _new_user(tenant_id, "c@example.com")
    db.add_all([u1, u2, u3])
    await db.commit()

    with pytest.raises(ScimError, match="displayName is required"):
        await _get_or_create_scim_group(db, tenant_id=tenant_id, display_name="   ")

    existing = await _get_or_create_scim_group(db, tenant_id=tenant_id, display_name="Ops Team")
    await db.commit()
    again = await _get_or_create_scim_group(
        db,
        tenant_id=tenant_id,
        display_name="Ops Team",
        external_id="ext-ops",
    )
    assert again.id == existing.id
    assert again.external_id == "ext-ops"

    resolved_ids, resolved_names = await _resolve_groups_from_refs(
        db,
        tenant_id=tenant_id,
        groups=[
            ScimGroupRef(display=None, value=None),
            ScimGroupRef(display="Ops Team", value=None),
            ScimGroupRef(display=None, value=str(existing.id)),
            ScimGroupRef(display=None, value=str(uuid.uuid4())),
            ScimGroupRef(display=None, value="raw-name"),
        ],
    )
    assert existing.id in resolved_ids
    assert "ops team" in resolved_names
    assert "raw-name" in resolved_names

    none_ids = await _resolve_member_user_ids(
        db,
        tenant_id=tenant_id,
        members=[ScimMemberRef(value="not-a-uuid", display=None)],
    )
    assert none_ids == set()

    member_ids = await _resolve_member_user_ids(
        db,
        tenant_id=tenant_id,
        members=[
            ScimMemberRef(value=str(u1.id), display=None),
            ScimMemberRef(value=str(uuid.uuid4()), display=None),
        ],
    )
    assert member_ids == {u1.id}

    g1 = await _get_or_create_scim_group(db, tenant_id=tenant_id, display_name="Group A")
    g2 = await _get_or_create_scim_group(db, tenant_id=tenant_id, display_name="Group B")
    await db.flush()

    first_impacted = await _set_group_memberships(
        db,
        tenant_id=tenant_id,
        group_id=g1.id,
        member_user_ids={u1.id, u2.id},
    )
    assert first_impacted == {u1.id, u2.id}
    await db.flush()

    second_impacted = await _set_group_memberships(
        db,
        tenant_id=tenant_id,
        group_id=g1.id,
        member_user_ids={u2.id, u3.id},
    )
    assert second_impacted == {u1.id, u2.id, u3.id}
    await db.flush()

    await _set_user_group_memberships(
        db,
        tenant_id=tenant_id,
        user_id=u2.id,
        group_ids={g2.id},
    )
    await db.commit()

    u2_rows = (
        await db.execute(
            select(ScimGroupMember.group_id).where(
                ScimGroupMember.tenant_id == tenant_id, ScimGroupMember.user_id == u2.id
            )
        )
    ).all()
    assert {row[0] for row in u2_rows} == {g2.id}


@pytest.mark.asyncio
async def test_scim_mappings_recompute_and_apply_helpers_cover_owner_and_defaults(
    db: AsyncSession,
) -> None:
    tenant_id, _ = await _seed_scim_tenant(
        db,
        mappings=[
            {"group": "engineering", "role": "member", "persona": "engineering"},
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
            {"group": "ops-admins", "role": "admin"},
            "skip",
        ],
    )
    settings = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    settings.scim_group_mappings = {"bad": "shape"}  # type: ignore[assignment]
    await db.commit()
    assert await _load_scim_group_mappings(db, tenant_id) == []

    settings.scim_group_mappings = [
        {"group": "engineering", "role": "member", "persona": "engineering"},
        {"group": "finops-admins", "role": "admin", "persona": "finance"},
        {"group": "ops-admins", "role": "admin"},
        "skip",
    ]
    await db.commit()
    mappings = await _load_scim_group_mappings(db, tenant_id)
    assert len(mappings) == 3

    owner = _new_user(
        tenant_id,
        "owner@example.com",
        role=UserRole.OWNER.value,
        persona=UserPersona.LEADERSHIP.value,
    )
    member = _new_user(
        tenant_id,
        "member@example.com",
        role=UserRole.MEMBER.value,
        persona=UserPersona.ENGINEERING.value,
    )
    ops_user = _new_user(
        tenant_id,
        "ops@example.com",
        role=UserRole.MEMBER.value,
        persona=UserPersona.PLATFORM.value,
    )
    no_group_user = _new_user(
        tenant_id,
        "nogroup@example.com",
        role=UserRole.ADMIN.value,
        persona=UserPersona.FINANCE.value,
    )
    db.add_all([owner, member, ops_user, no_group_user])
    await db.flush()

    g_finops = await _get_or_create_scim_group(
        db, tenant_id=tenant_id, display_name="FinOps-Admins"
    )
    g_engineering = await _get_or_create_scim_group(
        db, tenant_id=tenant_id, display_name="Engineering"
    )
    g_ops = await _get_or_create_scim_group(db, tenant_id=tenant_id, display_name="Ops-Admins")
    await db.flush()

    await _set_user_group_memberships(
        db,
        tenant_id=tenant_id,
        user_id=member.id,
        group_ids={g_finops.id, g_engineering.id},
    )
    await _set_user_group_memberships(
        db,
        tenant_id=tenant_id,
        user_id=ops_user.id,
        group_ids={g_ops.id},
    )
    await db.commit()

    group_names = await _load_user_group_names_from_memberships(
        db, tenant_id=tenant_id, user_id=member.id
    )
    assert "finops-admins" in group_names
    assert "engineering" in group_names

    await _recompute_entitlements_for_users(db, tenant_id=tenant_id, user_ids=set())
    await _recompute_entitlements_for_users(
        db,
        tenant_id=tenant_id,
        user_ids={owner.id, member.id, ops_user.id, no_group_user.id, uuid.uuid4()},
    )
    await db.commit()

    await db.refresh(owner)
    await db.refresh(member)
    await db.refresh(ops_user)
    await db.refresh(no_group_user)
    assert owner.role == UserRole.OWNER.value
    assert member.role == UserRole.ADMIN.value
    assert member.persona == UserPersona.ENGINEERING.value
    assert ops_user.role == UserRole.ADMIN.value
    assert ops_user.persona == UserPersona.PLATFORM.value
    assert no_group_user.role == UserRole.MEMBER.value

    # groups=None + for_create=False does not modify role/persona.
    member.role = UserRole.ADMIN.value
    member.persona = UserPersona.FINANCE.value
    await _apply_scim_group_mappings(
        db,
        tenant_id=tenant_id,
        user=member,
        groups=None,
        for_create=False,
    )
    assert member.role == UserRole.ADMIN.value
    assert member.persona == UserPersona.FINANCE.value

    # groups=None + for_create=True applies defaults.
    created_user = _new_user(tenant_id, "created@example.com", role="", persona="")
    db.add(created_user)
    await db.flush()
    await _apply_scim_group_mappings(
        db,
        tenant_id=tenant_id,
        user=created_user,
        groups=None,
        for_create=True,
    )
    assert created_user.role == UserRole.MEMBER.value
    assert created_user.persona == UserPersona.ENGINEERING.value

    # Owner is guardrailed from SCIM role/persona changes.
    await _apply_scim_group_mappings(
        db,
        tenant_id=tenant_id,
        user=owner,
        groups=[ScimGroupRef(value=None, display="FinOps-Admins")],
        for_create=False,
    )
    assert owner.role == UserRole.OWNER.value
