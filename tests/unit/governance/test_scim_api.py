import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, User
from app.models.tenant_identity_settings import TenantIdentitySettings


@pytest.mark.asyncio
async def test_scim_users_requires_bearer_token(ac: AsyncClient):
    res = await ac.get("/scim/v2/Users")
    assert res.status_code == 401
    payload = res.json()
    assert "schemas" in payload
    assert "urn:ietf:params:scim:api:messages:2.0:Error" in payload["schemas"]


@pytest.mark.asyncio
async def test_scim_schemas_endpoint_exposes_user_and_group_schemas(ac: AsyncClient):
    res = await ac.get("/scim/v2/Schemas")
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 2
    ids = {item.get("id") for item in payload.get("Resources", [])}
    assert "urn:ietf:params:scim:schemas:core:2.0:User" in ids
    assert "urn:ietf:params:scim:schemas:core:2.0:Group" in ids

    user_schema = next(
        item for item in payload["Resources"] if item["id"].endswith(":User")
    )
    group_schema = next(
        item for item in payload["Resources"] if item["id"].endswith(":Group")
    )
    assert any(
        attr.get("name") == "userName" for attr in user_schema.get("attributes", [])
    )
    assert any(
        attr.get("name") == "displayName" for attr in group_schema.get("attributes", [])
    )

    res = await ac.get(f"/scim/v2/Schemas/{user_schema['id']}")
    assert res.status_code == 200
    single = res.json()
    assert single["id"] == user_schema["id"]

    res = await ac.get(f"/scim/v2/Schemas/{group_schema['id']}")
    assert res.status_code == 200
    single = res.json()
    assert single["id"] == group_schema["id"]


@pytest.mark.asyncio
async def test_scim_user_lifecycle(ac: AsyncClient, db: AsyncSession):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="SCIM Tenant", plan="enterprise"))

    token = "scim-token-keep-this-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        scim_enabled=True,
        scim_bearer_token=token,
        scim_last_rotated_at=datetime.now(timezone.utc),
    )
    db.add(identity)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.get("/scim/v2/Users", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 0
    assert payload["Resources"] == []

    res = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "user1@example.com", "active": True},
    )
    assert res.status_code == 201
    created = res.json()
    assert created["userName"] == "user1@example.com"
    assert created["active"] is True
    user_id = created["id"]

    res = await ac.get("/scim/v2/Users", headers=headers)
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 1
    assert payload["Resources"][0]["id"] == user_id

    res = await ac.get(
        '/scim/v2/Users?filter=userName eq "user1@example.com"',
        headers=headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 1

    res = await ac.patch(
        f"/scim/v2/Users/{user_id}",
        headers=headers,
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
    )
    assert res.status_code == 200
    patched = res.json()
    assert patched["active"] is False

    res = await ac.delete(f"/scim/v2/Users/{user_id}", headers=headers)
    assert res.status_code == 204


@pytest.mark.asyncio
async def test_scim_group_mappings_apply_role_and_persona(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="SCIM Group Tenant", plan="enterprise"))

    token = "scim-token-keep-this-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        scim_enabled=True,
        scim_bearer_token=token,
        scim_last_rotated_at=datetime.now(timezone.utc),
        scim_group_mappings=[
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
        ],
    )
    db.add(identity)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={
            "userName": "user2@example.com",
            "active": True,
            "groups": [{"display": "FinOps-Admins"}],
        },
    )
    assert res.status_code == 201
    created = res.json()
    user_id = created["id"]

    user = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.id == uuid.UUID(user_id)
            )
        )
    ).scalar_one()
    assert user.role == "admin"
    assert user.persona == "finance"

    # PUT without `groups` should not change entitlements.
    res = await ac.put(
        f"/scim/v2/Users/{user_id}",
        headers=headers,
        json={"userName": "user2@example.com", "active": True},
    )
    assert res.status_code == 200
    await db.refresh(user)
    assert user.role == "admin"
    assert user.persona == "finance"

    # PUT with empty groups is authoritative and demotes to member.
    res = await ac.put(
        f"/scim/v2/Users/{user_id}",
        headers=headers,
        json={"userName": "user2@example.com", "active": True, "groups": []},
    )
    assert res.status_code == 200
    await db.refresh(user)
    assert user.role == "member"
    # Persona is UX-only: do not reset when groups are removed.
    assert user.persona == "finance"


@pytest.mark.asyncio
async def test_scim_groups_membership_updates_recompute_entitlements(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="SCIM Groups Tenant", plan="enterprise"))

    token = "scim-token-keep-this-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        scim_enabled=True,
        scim_bearer_token=token,
        scim_last_rotated_at=datetime.now(timezone.utc),
        scim_group_mappings=[
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
        ],
    )
    db.add(identity)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    # Create a user without groups: default member.
    res = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "user3@example.com", "active": True},
    )
    assert res.status_code == 201
    user_id = res.json()["id"]

    user = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.id == uuid.UUID(user_id)
            )
        )
    ).scalar_one()
    assert user.role == "member"

    # Create a group with this user as a member: should recompute role/persona based on mappings.
    res = await ac.post(
        "/scim/v2/Groups",
        headers=headers,
        json={"displayName": "FinOps-Admins", "members": [{"value": user_id}]},
    )
    assert res.status_code == 201
    created = res.json()
    assert created["displayName"] == "FinOps-Admins"
    group_id = created["id"]
    assert any(m.get("value") == user_id for m in created.get("members", []))

    await db.refresh(user)
    assert user.role == "admin"
    assert user.persona == "finance"

    # Filter listing by displayName.
    res = await ac.get(
        '/scim/v2/Groups?filter=displayName eq "FinOps-Admins"',
        headers=headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 1
    assert payload["Resources"][0]["id"] == group_id

    # Remove membership via path-filter remove.
    res = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [{"op": "remove", "path": f'members[value eq "{user_id}"]'}]
        },
    )
    assert res.status_code == 200
    await db.refresh(user)
    assert user.role == "member"
    # Persona is UX-only: do not reset when groups are removed.
    assert user.persona == "finance"


@pytest.mark.asyncio
async def test_scim_resource_types_includes_user_and_group(ac: AsyncClient):
    res = await ac.get("/scim/v2/ResourceTypes")
    assert res.status_code == 200
    payload = res.json()
    assert payload["totalResults"] == 2
    endpoints = {item.get("endpoint") for item in payload.get("Resources", [])}
    assert "/Users" in endpoints
    assert "/Groups" in endpoints


@pytest.mark.asyncio
async def test_scim_group_patch_no_path_replace_updates_membership(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="SCIM Patch Tenant", plan="enterprise"))

    token = "scim-token-keep-this-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        scim_enabled=True,
        scim_bearer_token=token,
        scim_last_rotated_at=datetime.now(timezone.utc),
        scim_group_mappings=[
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
        ],
    )
    db.add(identity)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    # Create a user without groups: default member.
    res = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "user4@example.com", "active": True},
    )
    assert res.status_code == 201
    user_id = res.json()["id"]

    user = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.id == uuid.UUID(user_id)
            )
        )
    ).scalar_one()
    assert user.role == "member"

    # Create a group with a staging name and no members.
    res = await ac.post(
        "/scim/v2/Groups",
        headers=headers,
        json={"displayName": "Staging Group", "members": []},
    )
    assert res.status_code == 201
    group_id = res.json()["id"]

    # Patch with no path and a dict body (common IdP variant): replace displayName + members together.
    res = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {
                    "op": "replace",
                    "value": {
                        "displayName": "FinOps-Admins",
                        "members": [{"value": user_id}],
                    },
                }
            ]
        },
    )
    assert res.status_code == 200

    await db.refresh(user)
    assert user.role == "admin"
    assert user.persona == "finance"


@pytest.mark.asyncio
async def test_scim_user_patch_groups_add_applies_mappings(
    ac: AsyncClient, db: AsyncSession
):
    tenant_id = uuid.uuid4()
    db.add(Tenant(id=tenant_id, name="SCIM User Patch Tenant", plan="enterprise"))

    token = "scim-token-keep-this-secret"
    identity = TenantIdentitySettings(
        tenant_id=tenant_id,
        sso_enabled=False,
        allowed_email_domains=[],
        scim_enabled=True,
        scim_bearer_token=token,
        scim_last_rotated_at=datetime.now(timezone.utc),
        scim_group_mappings=[
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
        ],
    )
    db.add(identity)
    await db.commit()

    headers = {"Authorization": f"Bearer {token}"}

    res = await ac.post(
        "/scim/v2/Users",
        headers=headers,
        json={"userName": "user5@example.com", "active": True},
    )
    assert res.status_code == 201
    created = res.json()
    user_id = created["id"]

    user = (
        await db.execute(
            select(User).where(
                User.tenant_id == tenant_id, User.id == uuid.UUID(user_id)
            )
        )
    ).scalar_one()
    assert user.role == "member"

    res = await ac.patch(
        f"/scim/v2/Users/{user_id}",
        headers=headers,
        json={
            "Operations": [
                {"op": "add", "path": "groups", "value": [{"display": "FinOps-Admins"}]}
            ]
        },
    )
    assert res.status_code == 200

    await db.refresh(user)
    assert user.role == "admin"
    assert user.persona == "finance"
