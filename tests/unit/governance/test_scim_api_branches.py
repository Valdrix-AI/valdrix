from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import Request
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scim_group import ScimGroupMember
from app.models.tenant import Tenant, User
from app.models.tenant_identity_settings import TenantIdentitySettings
from app.modules.governance.api.v1.scim import (
    ScimError,
    _apply_patch_operation,
    _extract_bearer_token,
    _resolve_entitlements_from_groups,
    _scim_group_resource,
    _scim_user_resource,
    scim_error_response,
)
from app.modules.governance.api.v1.scim_models import ScimPatchOperation


async def _seed_scim_tenant(
    db: AsyncSession,
    *,
    plan: str = "enterprise",
    scim_enabled: bool = True,
) -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    token = f"scim-token-{uuid.uuid4()}"
    db.add(Tenant(id=tenant_id, name=f"SCIM Tenant {tenant_id}", plan=plan))
    db.add(
        TenantIdentitySettings(
            tenant_id=tenant_id,
            sso_enabled=False,
            allowed_email_domains=[],
            scim_enabled=scim_enabled,
            scim_bearer_token=token,
            scim_last_rotated_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()
    return tenant_id, token


async def _create_scim_user(
    ac: AsyncClient, token: str, email: str, *, groups: list[dict[str, str]] | None = None
) -> str:
    payload: dict[str, object] = {"userName": email, "active": True}
    if groups is not None:
        payload["groups"] = groups
    res = await ac.post(
        "/scim/v2/Users",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def _create_scim_group(
    ac: AsyncClient,
    token: str,
    display_name: str,
    *,
    external_id: str | None = None,
    members: list[dict[str, str]] | None = None,
) -> str:
    payload: dict[str, object] = {"displayName": display_name}
    if external_id is not None:
        payload["externalId"] = external_id
    if members is not None:
        payload["members"] = members
    res = await ac.post(
        "/scim/v2/Groups",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def _request_with_auth(value: str | None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if value is not None:
        headers.append((b"authorization", value.encode()))
    return Request({"type": "http", "headers": headers})


def _assert_scim_error_payload(payload: dict[str, object], status: str) -> None:
    assert payload.get("status") == status
    assert "urn:ietf:params:scim:api:messages:2.0:Error" in list(
        payload.get("schemas", [])
    )


@pytest.mark.asyncio
async def test_scim_auth_rejects_invalid_token_disabled_and_non_enterprise(
    ac: AsyncClient, db: AsyncSession
) -> None:
    # Unknown token => invalidToken.
    res = await ac.get(
        "/scim/v2/Users", headers={"Authorization": "Bearer does-not-exist"}
    )
    assert res.status_code == 401
    _assert_scim_error_payload(res.json(), "401")
    assert res.json().get("scimType") == "invalidToken"

    # Valid token but SCIM disabled.
    _, disabled_token = await _seed_scim_tenant(db, plan="enterprise", scim_enabled=False)
    res = await ac.get(
        "/scim/v2/Users", headers={"Authorization": f"Bearer {disabled_token}"}
    )
    assert res.status_code == 403
    assert "disabled" in str(res.json().get("detail", "")).lower()

    # Valid token + SCIM enabled but non-enterprise tier.
    _, free_token = await _seed_scim_tenant(db, plan="free", scim_enabled=True)
    res = await ac.get("/scim/v2/Users", headers={"Authorization": f"Bearer {free_token}"})
    assert res.status_code == 403
    assert "enterprise tier" in str(res.json().get("detail", "")).lower()


@pytest.mark.asyncio
async def test_scim_list_users_validation_and_pagination_branches(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}

    assert (
        await ac.get("/scim/v2/Users?startIndex=0", headers=headers)
    ).status_code == 400
    assert (await ac.get("/scim/v2/Users?count=201", headers=headers)).status_code == 400
    invalid_filter = await ac.get(
        '/scim/v2/Users?filter=displayName eq "x"', headers=headers
    )
    assert invalid_filter.status_code == 400
    assert invalid_filter.json().get("scimType") == "invalidFilter"

    await _create_scim_user(ac, token, "page-a@example.com")
    await _create_scim_user(ac, token, "page-b@example.com")

    page = await ac.get("/scim/v2/Users?startIndex=2&count=1", headers=headers)
    assert page.status_code == 200
    body = page.json()
    assert body["totalResults"] == 2
    assert body["itemsPerPage"] == 1
    assert len(body["Resources"]) == 1

    zero = await ac.get("/scim/v2/Users?startIndex=2&count=0", headers=headers)
    assert zero.status_code == 200
    body = zero.json()
    assert body["itemsPerPage"] == 0
    assert body["Resources"] == []


@pytest.mark.asyncio
async def test_scim_user_get_put_patch_delete_invalid_id_and_not_found(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}
    missing = str(uuid.uuid4())

    assert (await ac.get("/scim/v2/Users/not-a-uuid", headers=headers)).status_code == 404
    assert (await ac.get(f"/scim/v2/Users/{missing}", headers=headers)).status_code == 404

    assert (
        await ac.put(
            "/scim/v2/Users/not-a-uuid",
            headers=headers,
            json={"userName": "x@example.com", "active": True},
        )
    ).status_code == 404
    assert (
        await ac.patch(
            "/scim/v2/Users/not-a-uuid",
            headers=headers,
            json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        )
    ).status_code == 404
    assert (await ac.delete("/scim/v2/Users/not-a-uuid", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_scim_patch_user_validation_error_branches(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _create_scim_user(ac, token, "patch-user@example.com")

    checks: list[tuple[dict[str, object], str]] = [
        (
            {"Operations": [{"op": "replace", "path": "active", "value": "true"}]},
            "active must be boolean",
        ),
        (
            {"Operations": [{"op": "remove", "path": "userName"}]},
            "userName cannot be removed",
        ),
        (
            {"Operations": [{"op": "replace", "path": "userName", "value": "bad"}]},
            "userName must be an email",
        ),
        (
            {"Operations": [{"op": "replace", "path": "emails", "value": []}]},
            "Unsupported patch path",
        ),
        (
            {"Operations": [{"op": "replace", "value": {"x": 1}}]},
            "Patch path is required",
        ),
        (
            {"Operations": [{"op": "add", "path": "groups", "value": {"display": "x"}}]},
            "groups patch value must be a list",
        ),
    ]

    for payload, expected in checks:
        res = await ac.patch(f"/scim/v2/Users/{user_id}", headers=headers, json=payload)
        assert res.status_code == 400
        assert expected in str(res.json().get("detail", ""))


@pytest.mark.asyncio
async def test_scim_groups_validation_filtering_and_get_errors(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}

    assert (
        await ac.get("/scim/v2/Groups?startIndex=0", headers=headers)
    ).status_code == 400
    assert (await ac.get("/scim/v2/Groups?count=201", headers=headers)).status_code == 400
    assert (
        await ac.get('/scim/v2/Groups?filter=userName eq "x"', headers=headers)
    ).status_code == 400

    group_id = await _create_scim_group(
        ac, token, "Infra-Team", external_id="ext-123", members=[]
    )
    by_external = await ac.get(
        '/scim/v2/Groups?filter=externalId eq "ext-123"', headers=headers
    )
    assert by_external.status_code == 200
    assert by_external.json()["totalResults"] == 1
    assert by_external.json()["Resources"][0]["id"] == group_id

    assert (await ac.get("/scim/v2/Groups/not-a-uuid", headers=headers)).status_code == 404
    assert (
        await ac.get(f"/scim/v2/Groups/{uuid.uuid4()}", headers=headers)
    ).status_code == 404


@pytest.mark.asyncio
async def test_scim_create_and_put_group_branch_paths(ac: AsyncClient, db: AsyncSession) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _create_scim_user(ac, token, "group-member@example.com")

    blank_display = await ac.post(
        "/scim/v2/Groups", headers=headers, json={"displayName": "   "}
    )
    assert blank_display.status_code == 400
    assert "displayName is required" in str(blank_display.json().get("detail"))

    group_id = await _create_scim_group(
        ac, token, "FinOps Team", members=[{"value": user_id}]
    )
    duplicate = await ac.post(
        "/scim/v2/Groups", headers=headers, json={"displayName": "FinOps Team"}
    )
    assert duplicate.status_code == 409

    second_group = await _create_scim_group(ac, token, "Another Team")

    put_invalid = await ac.put(
        "/scim/v2/Groups/not-a-uuid",
        headers=headers,
        json={"displayName": "Renamed", "members": []},
    )
    assert put_invalid.status_code == 404

    put_missing = await ac.put(
        f"/scim/v2/Groups/{uuid.uuid4()}",
        headers=headers,
        json={"displayName": "Renamed", "members": []},
    )
    assert put_missing.status_code == 404

    put_blank = await ac.put(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={"displayName": "   ", "members": []},
    )
    assert put_blank.status_code == 400

    put_ok = await ac.put(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={"displayName": "FinOps Admins", "externalId": "ext-new", "members": []},
    )
    assert put_ok.status_code == 200
    payload = put_ok.json()
    assert payload["displayName"] == "FinOps Admins"
    assert payload["externalId"] == "ext-new"
    assert payload["members"] == []

    # Keep second group used so optimizer doesn't skip branches with no members.
    assert second_group


@pytest.mark.asyncio
async def test_scim_patch_group_success_member_and_externalid_flows(
    ac: AsyncClient, db: AsyncSession
) -> None:
    tenant_id, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}

    # Mappings let us verify recompute branch effects on user role.
    settings = (
        await db.execute(
            select(TenantIdentitySettings).where(
                TenantIdentitySettings.tenant_id == tenant_id
            )
        )
    ).scalar_one()
    settings.scim_group_mappings = [{"group": "finops-admins", "role": "admin"}]
    await db.commit()

    user_a_id = await _create_scim_user(ac, token, "patch-group-a@example.com")
    user_b_id = await _create_scim_user(ac, token, "patch-group-b@example.com")
    group_id = await _create_scim_group(
        ac, token, "FinOps-Admins", members=[{"value": user_a_id}]
    )

    replace_members = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {
                    "op": "replace",
                    "path": "members",
                    "value": [{"value": user_a_id}, {"value": user_b_id}],
                }
            ]
        },
    )
    assert replace_members.status_code == 200
    assert len(replace_members.json().get("members", [])) == 2

    add_member = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {"op": "add", "path": "members", "value": {"value": user_a_id}}
            ]
        },
    )
    assert add_member.status_code == 200

    remove_one = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {
                    "op": "remove",
                    "path": "members",
                    "value": [{"value": user_b_id}],
                }
            ]
        },
    )
    assert remove_one.status_code == 200
    assert len(remove_one.json().get("members", [])) == 1

    # No path + dict variant updates displayName and externalId together.
    no_path_variant = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {
                    "op": "replace",
                    "value": {
                        "displayName": "FinOps-Admins",
                        "externalId": "idp-group-9",
                        "members": [{"value": user_a_id}],
                    },
                }
            ]
        },
    )
    assert no_path_variant.status_code == 200
    assert no_path_variant.json()["externalId"] == "idp-group-9"

    remove_external = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={"Operations": [{"op": "remove", "path": "externalId"}]},
    )
    assert remove_external.status_code == 200
    assert "externalId" not in remove_external.json()

    remove_via_path_filter = await ac.patch(
        f"/scim/v2/Groups/{group_id}",
        headers=headers,
        json={
            "Operations": [
                {"op": "remove", "path": f'members[value eq "{user_a_id}"]', "value": None}
            ]
        },
    )
    assert remove_via_path_filter.status_code == 200
    assert remove_via_path_filter.json().get("members") == []

    user_a = (
        await db.execute(
            select(User).where(User.tenant_id == tenant_id, User.id == uuid.UUID(user_a_id))
        )
    ).scalar_one()
    assert user_a.role == "member"


@pytest.mark.asyncio
async def test_scim_patch_group_validation_error_branches(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}
    group_id = await _create_scim_group(ac, token, "Patch-Errors", members=[])

    checks: list[tuple[dict[str, object], str]] = [
        (
            {"Operations": [{"op": "replace", "value": "not-a-dict"}]},
            "Patch path is required",
        ),
        (
            {"Operations": [{"op": "remove", "path": "displayName"}]},
            "displayName cannot be removed",
        ),
        (
            {"Operations": [{"op": "replace", "path": "displayName", "value": 1}]},
            "displayName must be string",
        ),
        (
            {"Operations": [{"op": "replace", "path": "displayName", "value": "   "}]},
            "displayName is required",
        ),
        (
            {"Operations": [{"op": "replace", "path": "externalId", "value": 1}]},
            "externalId must be string",
        ),
        (
            {"Operations": [{"op": "replace", "path": "members", "value": {"v": 1}}]},
            "members patch value must be a list",
        ),
        (
            {"Operations": [{"op": "add", "path": "members", "value": 1}]},
            "members add value must be list or object",
        ),
        (
            {"Operations": [{"op": "remove", "path": "members", "value": 1}]},
            "members remove value must be list or object",
        ),
        (
            {"Operations": [{"op": "replace", "path": "name", "value": "x"}]},
            "Unsupported patch path",
        ),
    ]

    for payload, expected in checks:
        res = await ac.patch(f"/scim/v2/Groups/{group_id}", headers=headers, json=payload)
        assert res.status_code == 400
        assert expected in str(res.json().get("detail", ""))


@pytest.mark.asyncio
async def test_scim_delete_group_success_invalid_and_not_found(
    ac: AsyncClient, db: AsyncSession
) -> None:
    _, token = await _seed_scim_tenant(db)
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _create_scim_user(ac, token, "delete-member@example.com")
    group_id = await _create_scim_group(
        ac, token, "Delete-Target", members=[{"value": user_id}]
    )

    before = await db.execute(select(ScimGroupMember))
    assert len(list(before.scalars().all())) == 1

    deleted = await ac.delete(f"/scim/v2/Groups/{group_id}", headers=headers)
    assert deleted.status_code == 204

    assert (await ac.delete("/scim/v2/Groups/not-a-uuid", headers=headers)).status_code == 404
    assert (
        await ac.delete(f"/scim/v2/Groups/{uuid.uuid4()}", headers=headers)
    ).status_code == 404


def test_scim_helpers_extract_token_and_error_response() -> None:
    assert _extract_bearer_token(_request_with_auth("Bearer token-1")) == "token-1"
    assert _extract_bearer_token(_request_with_auth("bearer token-2")) == "token-2"

    with pytest.raises(ScimError, match="Missing or invalid Authorization header"):
        _extract_bearer_token(_request_with_auth(None))
    with pytest.raises(ScimError, match="Missing or invalid Authorization header"):
        _extract_bearer_token(_request_with_auth("Bearer   "))

    response = scim_error_response(ScimError(401, "bad auth", scim_type="invalidToken"))
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert b'"scimType":"invalidToken"' in response.body


def test_scim_helpers_build_resources_and_resolve_entitlements() -> None:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    group_id = uuid.uuid4()

    user = SimpleNamespace(id=user_id, email="member@example.com", is_active=True)
    user_payload = _scim_user_resource(
        user,
        base_url="https://example.com/",
        tenant_id=tenant_id,
        groups=[{"value": str(group_id), "display": "FinOps"}],
    )
    assert user_payload["id"] == str(user_id)
    assert user_payload["groups"][0]["value"] == str(group_id)

    group = SimpleNamespace(id=group_id, display_name="FinOps", external_id="idp-9")
    group_payload = _scim_group_resource(
        group,
        base_url="https://example.com/",
        members=[{"value": str(user_id), "display": "member@example.com"}],
    )
    assert group_payload["externalId"] == "idp-9"
    assert group_payload["members"][0]["value"] == str(user_id)

    role, persona = _resolve_entitlements_from_groups(
        {"finops-admins", "engineering"},
        [
            {"group": "engineering", "role": "member", "persona": "engineering"},
            {"group": "finops-admins", "role": "admin", "persona": "finance"},
        ],
    )
    assert role == "admin"
    assert persona == "engineering"


def test_scim_apply_patch_operation_branches_direct() -> None:
    user = SimpleNamespace(email="old@example.com", is_active=True)

    # Supported operations.
    _apply_patch_operation(user, ScimPatchOperation(op="replace", path="active", value=False))
    assert user.is_active is False
    _apply_patch_operation(
        user, ScimPatchOperation(op="replace", path="userName", value="new@example.com")
    )
    assert user.email == "new@example.com"
    _apply_patch_operation(user, ScimPatchOperation(op="remove", path="active", value=None))
    assert user.is_active is False

    # Unsupported op via simple object (runtime check branch).
    with pytest.raises(ScimError, match="Unsupported patch op"):
        _apply_patch_operation(
            user, SimpleNamespace(op="move", path="active", value=True)  # type: ignore[arg-type]
        )

    with pytest.raises(ScimError, match="Patch path is required"):
        _apply_patch_operation(user, ScimPatchOperation(op="replace", path=None, value=True))
    with pytest.raises(ScimError, match="active must be boolean"):
        _apply_patch_operation(user, ScimPatchOperation(op="replace", path="active", value="x"))
    with pytest.raises(ScimError, match="userName cannot be removed"):
        _apply_patch_operation(user, ScimPatchOperation(op="remove", path="userName", value=None))
    with pytest.raises(ScimError, match="userName must be an email"):
        _apply_patch_operation(
            user, ScimPatchOperation(op="replace", path="userName", value="not-email")
        )
    with pytest.raises(ScimError, match="Unsupported patch path"):
        _apply_patch_operation(user, ScimPatchOperation(op="replace", path="emails", value=[]))
