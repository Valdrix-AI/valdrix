from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from sqlalchemy.exc import IntegrityError

import app.modules.governance.api.v1.scim as scim
from app.modules.governance.api.v1.scim_models import (
    ScimGroupCreate,
    ScimGroupPut,
    ScimMemberRef,
    ScimPatchOperation,
    ScimPatchRequest,
    ScimUserCreate,
    ScimUserPut,
)


class _FakeScalars:
    def __init__(self, values: list[Any] | None = None):
        self._values = list(values or [])

    def all(self) -> list[Any]:
        return list(self._values)

    def first(self) -> Any | None:
        return self._values[0] if self._values else None


@dataclass
class _FakeResult:
    one: Any | None = None
    values: list[Any] | None = None
    rows: list[Any] | None = None

    def scalar_one_or_none(self) -> Any | None:
        return self.one

    def scalar_one(self) -> Any:
        if self.one is None:
            raise AssertionError("scalar_one called but one is None")
        return self.one

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.values)

    def all(self) -> list[Any]:
        return list(self.rows or [])


class _NoAutoflush:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class _FakeDB:
    def __init__(
        self,
        execute_results: list[_FakeResult | Exception] | None = None,
        *,
        flush_effect: Exception | None = None,
        commit_effects: list[Exception | None] | None = None,
    ):
        self._execute_results = list(execute_results or [])
        self.flush_effect = flush_effect
        self.commit_effects = list(commit_effects or [])
        self.added: list[Any] = []
        self.rollback_calls = 0
        self.commit_calls = 0
        self.no_autoflush = _NoAutoflush()

    async def execute(self, _stmt: Any) -> _FakeResult:
        if not self._execute_results:
            return _FakeResult()
        nxt = self._execute_results.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        if self.flush_effect is not None:
            raise self.flush_effect

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.commit_effects:
            effect = self.commit_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect

    async def rollback(self) -> None:
        self.rollback_calls += 1


def _request(path: str, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 443),
        }
    )


def _ctx() -> scim.ScimContext:
    return scim.ScimContext(tenant_id=uuid4())


def _user(email: str = "user@example.com") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email=email,
        is_active=True,
        role="member",
        persona="engineering",
    )


def _group(name: str = "Ops Team") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        display_name=name,
        display_name_norm=name.lower(),
        external_id=None,
        external_id_norm=None,
    )


def _integrity_error() -> IntegrityError:
    return IntegrityError("insert", {}, Exception("duplicate"))


@pytest.mark.asyncio
async def test_scim_helper_none_and_empty_branches() -> None:
    tenant_id = uuid4()
    user = _user()
    group = _group()

    user_payload = scim._scim_user_resource(
        user,
        base_url="https://example.test/",
        tenant_id=tenant_id,
        groups=None,
    )
    assert "groups" not in user_payload

    group_payload = scim._scim_group_resource(
        group, base_url="https://example.test/", members=None
    )
    assert "members" not in group_payload

    role, persona = scim._resolve_entitlements_from_groups(
        {"engineering"},
        [{"group": "engineering", "role": "member", "persona": "finance"}],
    )
    assert role == "member"
    assert persona == "finance"

    db_with_no_mappings = _FakeDB([_FakeResult(one=None)])
    assert await scim._load_scim_group_mappings(db_with_no_mappings, tenant_id) == []

    member_db = _FakeDB([_FakeResult(rows=[])])
    assert (
        await scim._load_group_member_user_ids(
            member_db, tenant_id=tenant_id, group_id=uuid4()
        )
        == set()
    )


@pytest.mark.asyncio
async def test_scim_schema_and_user_filter_direct_branches() -> None:
    request = _request("/scim/v2/Schemas")
    schemas_payload = await scim.list_schemas(request)
    assert schemas_payload["totalResults"] == 2

    user_schema = await scim.get_schema(request, scim.SCIM_USER_SCHEMA)
    assert user_schema.status_code == 200
    group_schema = await scim.get_schema(request, scim.SCIM_GROUP_SCHEMA)
    assert group_schema.status_code == 200

    ctx = _ctx()
    user = _user("target@example.com")
    list_db = _FakeDB([_FakeResult(values=[user])])
    with patch.object(
        scim,
        "_load_user_group_refs_map",
        new=AsyncMock(return_value={user.id: []}),
    ):
        payload = await scim.list_users(
            request=_request("/scim/v2/Users"),
            startIndex=1,
            count=10,
            filter='userName eq "target@example.com"',
            ctx=ctx,
            db=list_db,
        )
    assert payload.totalResults == 1

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.get_user(
            request=_request("/scim/v2/Users/missing"),
            user_id=str(uuid4()),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )


@pytest.mark.asyncio
async def test_scim_user_direct_list_get_create_paths() -> None:
    ctx = _ctx()
    user = _user("list@example.com")

    list_db = _FakeDB([_FakeResult(values=[user])])
    with patch.object(
        scim,
        "_load_user_group_refs_map",
        new=AsyncMock(return_value={user.id: [{"value": "g1", "display": "Ops"}]}),
    ):
        payload = await scim.list_users(
            request=_request("/scim/v2/Users"),
            startIndex=1,
            count=10,
            filter=None,
            ctx=ctx,
            db=list_db,
        )
    assert payload.totalResults == 1
    assert payload.itemsPerPage == 1
    assert payload.Resources[0]["id"] == str(user.id)

    get_db = _FakeDB([_FakeResult(one=user)])
    with patch.object(
        scim,
        "_load_user_group_refs_map",
        new=AsyncMock(return_value={user.id: []}),
    ):
        response = await scim.get_user(
            request=_request(f"/scim/v2/Users/{user.id}"),
            user_id=str(user.id),
            ctx=ctx,
            db=get_db,
        )
    assert response.status_code == 200

    flush_conflict_db = _FakeDB(flush_effect=_integrity_error())
    with patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()):
        with pytest.raises(scim.ScimError, match="User already exists"):
            await scim.create_user(
                request=_request("/scim/v2/Users", method="POST"),
                body=ScimUserCreate(userName="flush@example.com", active=True),
                ctx=ctx,
                db=flush_conflict_db,
            )
    assert flush_conflict_db.rollback_calls == 1

    commit_conflict_db = _FakeDB(commit_effects=[_integrity_error()])
    with patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()):
        with pytest.raises(scim.ScimError, match="User already exists"):
            await scim.create_user(
                request=_request("/scim/v2/Users", method="POST"),
                body=ScimUserCreate(userName="commit@example.com", active=True),
                ctx=ctx,
                db=commit_conflict_db,
            )
    assert commit_conflict_db.rollback_calls == 1

    ok_db = _FakeDB(commit_effects=[None, None])
    with (
        patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()),
        patch.object(scim, "_load_user_group_refs_map", new=AsyncMock(return_value={})),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.create_user(
            request=_request("/scim/v2/Users", method="POST"),
            body=ScimUserCreate(userName="ok@example.com", active=True),
            ctx=ctx,
            db=ok_db,
        )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_scim_user_direct_put_patch_delete_paths() -> None:
    ctx = _ctx()
    user = _user("existing@example.com")

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.put_user(
            request=_request("/scim/v2/Users/1", method="PUT"),
            user_id=str(uuid4()),
            body=ScimUserPut(userName="new@example.com", active=True),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    put_conflict_db = _FakeDB([_FakeResult(one=user)], commit_effects=[_integrity_error()])
    with patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()):
        with pytest.raises(scim.ScimError, match="User already exists"):
            await scim.put_user(
                request=_request(f"/scim/v2/Users/{user.id}", method="PUT"),
                user_id=str(user.id),
                body=ScimUserPut(userName="dup@example.com", active=True),
                ctx=ctx,
                db=put_conflict_db,
            )
    assert put_conflict_db.rollback_calls == 1

    put_ok_db = _FakeDB([_FakeResult(one=user)], commit_effects=[None, None])
    with (
        patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()),
        patch.object(scim, "_load_user_group_refs_map", new=AsyncMock(return_value={})),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.put_user(
            request=_request(f"/scim/v2/Users/{user.id}", method="PUT"),
            user_id=str(user.id),
            body=ScimUserPut(userName="updated@example.com", active=False),
            ctx=ctx,
            db=put_ok_db,
        )
    assert response.status_code == 200

    patch_user_not_found_db = _FakeDB([_FakeResult(one=None)])
    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.patch_user(
            request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
            user_id=str(user.id),
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="replace", path="active", value=False)]
            ),
            ctx=ctx,
            db=patch_user_not_found_db,
        )

    patch_invalid_groups_db = _FakeDB([_FakeResult(one=user)])
    with patch.object(scim, "_load_user_group_refs_map", new=AsyncMock(return_value={})):
        with pytest.raises(scim.ScimError, match="groups patch value must be a list"):
            await scim.patch_user(
                request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
                user_id=str(user.id),
                body=ScimPatchRequest(
                    Operations=[
                        ScimPatchOperation(
                            op="add",
                            path="groups",
                            value={"display": "ops"},
                        )
                    ]
                ),
                ctx=ctx,
                db=patch_invalid_groups_db,
            )

    patch_unsupported_groups_db = _FakeDB([_FakeResult(one=user)])
    with patch.object(scim, "_load_user_group_refs_map", new=AsyncMock(return_value={})):
        with pytest.raises(scim.ScimError, match="Unsupported patch op for groups"):
            await scim.patch_user(
                request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
                user_id=str(user.id),
                body=SimpleNamespace(
                    Operations=[
                        SimpleNamespace(op="move", path="groups", value=[])
                    ]
                ),
                ctx=ctx,
                db=patch_unsupported_groups_db,
            )

    patch_commit_conflict_db = _FakeDB(
        [_FakeResult(one=user)], commit_effects=[_integrity_error()]
    )
    with pytest.raises(scim.ScimError, match="User already exists"):
        await scim.patch_user(
            request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
            user_id=str(user.id),
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="replace", path="active", value=False)]
            ),
            ctx=ctx,
            db=patch_commit_conflict_db,
        )
    assert patch_commit_conflict_db.rollback_calls == 1

    patch_ok_db = _FakeDB([_FakeResult(one=user)], commit_effects=[None, None])
    existing_group_id = uuid4()
    new_group_id = uuid4()
    with (
        patch.object(
            scim,
            "_load_user_group_refs_map",
            new=AsyncMock(
                side_effect=[
                    {
                        user.id: [
                            {"value": str(existing_group_id), "display": "Existing"}
                        ]
                    },
                    {user.id: [{"value": str(new_group_id), "display": "New"}]},
                ]
            ),
        ),
        patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.patch_user(
            request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
            user_id=str(user.id),
            body=ScimPatchRequest(
                Operations=[
                    ScimPatchOperation(
                        op="replace",
                        path="groups",
                        value=[{"value": str(new_group_id), "display": "New"}],
                    )
                ]
            ),
            ctx=ctx,
            db=patch_ok_db,
        )
    assert response.status_code == 200

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.delete_user(
            user_id=str(uuid4()),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    delete_ok_db = _FakeDB([_FakeResult(one=user)], commit_effects=[None, None])
    with patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls:
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.delete_user(
            user_id=str(user.id),
            ctx=ctx,
            db=delete_ok_db,
        )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_scim_apply_mappings_and_patch_user_remove_groups_branches() -> None:
    ctx = _ctx()
    user = _user("mapping@example.com")
    user.role = "member"
    user.persona = ""

    with (
        patch.object(
            scim,
            "_resolve_groups_from_refs",
            new=AsyncMock(return_value=({uuid4()}, {"ops-team"})),
        ),
        patch.object(scim, "_set_user_group_memberships", new=AsyncMock()),
        patch.object(scim, "_load_scim_group_mappings", new=AsyncMock(return_value=[])),
    ):
        await scim._apply_scim_group_mappings(
            _FakeDB(),
            tenant_id=ctx.tenant_id,
            user=user,
            groups=[scim.ScimGroupRef(value=None, display="Ops-Team")],
            for_create=True,
        )
    assert user.role == "member"
    assert user.persona == "engineering"

    patch_db = _FakeDB([_FakeResult(one=user)], commit_effects=[None, None])
    with (
        patch.object(
            scim,
            "_load_user_group_refs_map",
            new=AsyncMock(side_effect=[{user.id: [{"value": str(uuid4()), "display": "Old"}]}, {user.id: []}]),
        ),
        patch.object(scim, "_apply_scim_group_mappings", new=AsyncMock()),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.patch_user(
            request=_request(f"/scim/v2/Users/{user.id}", method="PATCH"),
            user_id=str(user.id),
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="remove", path="groups", value=None)]
            ),
            ctx=ctx,
            db=patch_db,
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_scim_groups_direct_list_create_get_put_paths() -> None:
    ctx = _ctx()
    group = _group("FinOps Admins")
    group.external_id = "ext-1"
    group.external_id_norm = "ext-1"

    list_db = _FakeDB([_FakeResult(values=[group]), _FakeResult(values=[group])])
    with patch.object(
        scim,
        "_load_group_member_refs_map",
        new=AsyncMock(return_value={group.id: []}),
    ):
        payload = await scim.list_groups(
            request=_request("/scim/v2/Groups"),
            startIndex=1,
            count=10,
            filter='displayName eq "FinOps Admins"',
            ctx=ctx,
            db=list_db,
        )
        payload_by_external = await scim.list_groups(
            request=_request("/scim/v2/Groups"),
            startIndex=1,
            count=10,
            filter='externalId eq "ext-1"',
            ctx=ctx,
            db=list_db,
        )
    assert payload.totalResults == 1
    assert payload_by_external.totalResults == 1

    with pytest.raises(scim.ScimError, match="Group already exists"):
        await scim.create_group(
            request=_request("/scim/v2/Groups", method="POST"),
            body=ScimGroupCreate(displayName="Conflict Team"),
            ctx=ctx,
            db=_FakeDB(flush_effect=_integrity_error()),
        )

    create_without_members_db = _FakeDB(commit_effects=[None, None])
    with (
        patch.object(
            scim,
            "_load_group_member_refs_map",
            new=AsyncMock(return_value={}),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        create_without_members_response = await scim.create_group(
            request=_request("/scim/v2/Groups", method="POST"),
            body=ScimGroupCreate(displayName="No Member Team"),
            ctx=ctx,
            db=create_without_members_db,
        )
    assert create_without_members_response.status_code == 201

    member_id = uuid4()
    create_db = _FakeDB(commit_effects=[None, None])
    with (
        patch.object(scim, "_resolve_member_user_ids", new=AsyncMock(return_value={member_id})),
        patch.object(scim, "_set_group_memberships", new=AsyncMock(return_value={member_id})),
        patch.object(
            scim,
            "_recompute_entitlements_for_users",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            scim,
            "_load_group_member_refs_map",
            new=AsyncMock(return_value={}),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        response = await scim.create_group(
            request=_request("/scim/v2/Groups", method="POST"),
            body=ScimGroupCreate(
                displayName="Create Team",
                members=[ScimMemberRef(value=str(member_id), display=None)],
            ),
            ctx=ctx,
            db=create_db,
        )
    assert response.status_code == 201

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.get_group(
            request=_request("/scim/v2/Groups/missing"),
            group_id=str(uuid4()),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    get_db = _FakeDB([_FakeResult(one=group)])
    with patch.object(
        scim,
        "_load_group_member_refs_map",
        new=AsyncMock(return_value={group.id: []}),
    ):
        get_response = await scim.get_group(
            request=_request(f"/scim/v2/Groups/{group.id}"),
            group_id=str(group.id),
            ctx=ctx,
            db=get_db,
        )
    assert get_response.status_code == 200

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.put_group(
            request=_request("/scim/v2/Groups/missing", method="PUT"),
            group_id=str(uuid4()),
            body=ScimGroupPut(displayName="Missing", members=[]),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    with pytest.raises(scim.ScimError, match="displayName is required"):
        await scim.put_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PUT"),
            group_id=str(group.id),
            body=ScimGroupPut(displayName="   ", members=[]),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=group)]),
        )

    put_conflict_db = _FakeDB([_FakeResult(one=group)], commit_effects=[_integrity_error()])
    with pytest.raises(scim.ScimError, match="Group already exists"):
        await scim.put_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PUT"),
            group_id=str(group.id),
            body=ScimGroupPut(displayName="Conflict", members=[]),
            ctx=ctx,
            db=put_conflict_db,
        )

    put_without_members_db = _FakeDB([_FakeResult(one=group)], commit_effects=[None, None])
    with (
        patch.object(
            scim,
            "_load_group_member_refs_map",
            new=AsyncMock(return_value={group.id: []}),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        put_without_members_response = await scim.put_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PUT"),
            group_id=str(group.id),
            body=ScimGroupPut(displayName="Renamed No Members", members=None),
            ctx=ctx,
            db=put_without_members_db,
        )
    assert put_without_members_response.status_code == 200

    put_ok_db = _FakeDB([_FakeResult(one=group)], commit_effects=[None, None])
    with (
        patch.object(scim, "_resolve_member_user_ids", new=AsyncMock(return_value={member_id})),
        patch.object(scim, "_set_group_memberships", new=AsyncMock(return_value={member_id})),
        patch.object(
            scim,
            "_recompute_entitlements_for_users",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            scim,
            "_load_group_member_refs_map",
            new=AsyncMock(return_value={group.id: []}),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        put_response = await scim.put_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PUT"),
            group_id=str(group.id),
            body=ScimGroupPut(
                displayName="Renamed Team",
                externalId="ext-2",
                members=[ScimMemberRef(value=str(member_id), display=None)],
            ),
            ctx=ctx,
            db=put_ok_db,
        )
    assert put_response.status_code == 200


@pytest.mark.asyncio
async def test_scim_patch_group_direct_variants_and_delete_paths() -> None:
    ctx = _ctx()
    group = _group("Patch Team")
    user_id = uuid4()
    second_user_id = uuid4()

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.patch_group(
            request=_request("/scim/v2/Groups/not-a-uuid", method="PATCH"),
            group_id="not-a-uuid",
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="replace", path="displayName", value="x")]
            ),
            ctx=ctx,
            db=_FakeDB(),
        )

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.patch_group(
            request=_request("/scim/v2/Groups/missing", method="PATCH"),
            group_id=str(uuid4()),
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="replace", path="displayName", value="x")]
            ),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    invalid_no_path_db = _FakeDB([_FakeResult(one=group)])
    with pytest.raises(scim.ScimError, match="members must be a list"):
        await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=ScimPatchRequest(
                Operations=[
                    ScimPatchOperation(
                        op="replace",
                        value={"displayName": "New", "members": "bad"},
                    )
                ]
            ),
            ctx=ctx,
            db=invalid_no_path_db,
        )

    blank_name_db = _FakeDB([_FakeResult(one=group)])
    with pytest.raises(scim.ScimError, match="displayName is required"):
        await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=SimpleNamespace(
                Operations=[
                    SimpleNamespace(op="replace", path=None, value={"displayName": "   "})
                ]
            ),
            ctx=ctx,
            db=blank_name_db,
        )

    no_path_non_dict_db = _FakeDB([_FakeResult(one=group)])
    with pytest.raises(scim.ScimError, match="Patch path is required"):
        await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=SimpleNamespace(
                Operations=[SimpleNamespace(op="replace", path=None, value="bad-value")]
            ),
            ctx=ctx,
            db=no_path_non_dict_db,
        )

    validation_cases: list[tuple[Any, str]] = [
        (ScimPatchOperation(op="remove", path="displayName", value=None), "cannot be removed"),
        (ScimPatchOperation(op="replace", path="displayName", value=123), "must be string"),
        (ScimPatchOperation(op="replace", path="displayName", value="   "), "is required"),
        (ScimPatchOperation(op="replace", path="externalId", value=123), "must be string"),
        (
            ScimPatchOperation(op="replace", path="members", value={"value": str(user_id)}),
            "must be a list",
        ),
        (ScimPatchOperation(op="add", path="members", value=1), "must be list or object"),
        (ScimPatchOperation(op="remove", path="members", value=1), "must be list or object"),
        (ScimPatchOperation(op="replace", path="name", value="x"), "Unsupported patch path"),
    ]
    for operation, expected in validation_cases:
        with pytest.raises(scim.ScimError, match=expected):
            await scim.patch_group(
                request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
                group_id=str(group.id),
                body=ScimPatchRequest(Operations=[operation]),
                ctx=ctx,
                db=_FakeDB([_FakeResult(one=group)]),
            )

    with pytest.raises(scim.ScimError, match="Unsupported patch op"):
        await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=SimpleNamespace(
                Operations=[SimpleNamespace(op="move", path="displayName", value="x")]
            ),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=group)]),
        )

    patch_ok_db = _FakeDB([_FakeResult(one=group)], commit_effects=[None, None])
    with (
        patch.object(
            scim,
            "_load_group_member_user_ids",
            new=AsyncMock(return_value={user_id}),
        ),
        patch.object(
            scim, "_resolve_member_user_ids", new=AsyncMock(return_value={second_user_id})
        ),
        patch.object(
            scim,
            "_set_group_memberships",
            new=AsyncMock(return_value={user_id, second_user_id}),
        ),
        patch.object(
            scim,
            "_recompute_entitlements_for_users",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            scim,
            "_load_group_member_refs_map",
            new=AsyncMock(return_value={group.id: []}),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        patch_response = await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=ScimPatchRequest(
                Operations=[
                    ScimPatchOperation(
                        op="replace",
                        value={
                            "displayName": "Renamed Team",
                            "externalId": "ext-1",
                            "members": [{"value": str(second_user_id)}],
                        },
                    ),
                    ScimPatchOperation(
                        op="replace",
                        path="members",
                        value=[{"value": str(second_user_id)}],
                    ),
                    ScimPatchOperation(
                        op="add",
                        path="members",
                        value={"value": str(second_user_id)},
                    ),
                    ScimPatchOperation(
                        op="add",
                        path="members",
                        value=[{"value": str(second_user_id)}],
                    ),
                    ScimPatchOperation(
                        op="remove",
                        path=f'members[value eq "{user_id}"]',
                        value=None,
                    ),
                    ScimPatchOperation(
                        op="remove",
                        path="members",
                        value={"value": str(second_user_id)},
                    ),
                    ScimPatchOperation(
                        op="remove",
                        path="members",
                        value=[{"value": str(second_user_id)}],
                    ),
                    ScimPatchOperation(op="remove", path="members", value=None),
                    ScimPatchOperation(op="replace", path="externalId", value="ext-2"),
                    ScimPatchOperation(op="remove", path="externalId", value=None),
                    ScimPatchOperation(op="replace", path="displayName", value="Final Name"),
                ]
            ),
            ctx=ctx,
            db=patch_ok_db,
        )
    assert patch_response.status_code == 200

    patch_conflict_db = _FakeDB([_FakeResult(one=group)], commit_effects=[_integrity_error()])
    with pytest.raises(scim.ScimError, match="Group already exists"):
        await scim.patch_group(
            request=_request(f"/scim/v2/Groups/{group.id}", method="PATCH"),
            group_id=str(group.id),
            body=ScimPatchRequest(
                Operations=[ScimPatchOperation(op="replace", path="displayName", value="X")]
            ),
            ctx=ctx,
            db=patch_conflict_db,
        )
    assert patch_conflict_db.rollback_calls == 1

    with pytest.raises(scim.ScimError, match="Resource not found"):
        await scim.delete_group(
            group_id=str(uuid4()),
            ctx=ctx,
            db=_FakeDB([_FakeResult(one=None)]),
        )

    delete_ok_db = _FakeDB([_FakeResult(one=group), _FakeResult()], commit_effects=[None, None])
    with (
        patch.object(
            scim,
            "_load_group_member_user_ids",
            new=AsyncMock(return_value={user_id}),
        ),
        patch.object(
            scim,
            "_recompute_entitlements_for_users",
            new=AsyncMock(return_value=None),
        ),
        patch("app.modules.governance.api.v1.scim.AuditLogger") as audit_logger_cls,
    ):
        audit_logger_cls.return_value.log = AsyncMock()
        delete_response = await scim.delete_group(
            group_id=str(group.id),
            ctx=ctx,
            db=delete_ok_db,
        )
    assert delete_response.status_code == 204
