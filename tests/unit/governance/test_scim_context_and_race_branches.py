from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from sqlalchemy.exc import IntegrityError

from app.modules.governance.api.v1.scim import (
    ScimError,
    _get_or_create_scim_group,
    get_scim_context,
)


def _auth_request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
    )


class _FirstResult:
    def __init__(self, row: object | None):
        self._row = row

    def first(self) -> object | None:
        return self._row


class _ScalarResult:
    def __init__(self, value: object | None):
        self._value = value

    def scalar_one_or_none(self) -> object | None:
        return self._value


class _SequentialDB:
    def __init__(self, results: list[object]):
        self._results = list(results)

    async def execute(self, _stmt: object) -> object:
        if not self._results:
            raise AssertionError("No fake DB results configured")
        return self._results.pop(0)


def _session_maker_for(db: object):
    @asynccontextmanager
    async def _session_scope():
        yield db

    return _session_scope


@pytest.mark.asyncio
async def test_get_scim_context_additional_branches() -> None:
    tenant_id = uuid4()
    request = _auth_request("token-x")

    unauthorized_db = _SequentialDB([_FirstResult(None)])
    with (
        patch("app.modules.governance.api.v1.scim.generate_secret_blind_index", return_value="bidx"),
        patch(
            "app.modules.governance.api.v1.scim.db_session.async_session_maker",
            new=_session_maker_for(unauthorized_db),
        ),
    ):
        with pytest.raises(ScimError, match="Unauthorized"):
            await get_scim_context(request)

    disabled_db = _SequentialDB([_FirstResult((tenant_id, False))])
    with (
        patch("app.modules.governance.api.v1.scim.generate_secret_blind_index", return_value="bidx"),
        patch(
            "app.modules.governance.api.v1.scim.db_session.async_session_maker",
            new=_session_maker_for(disabled_db),
        ),
    ):
        with pytest.raises(ScimError, match="disabled"):
            await get_scim_context(request)

    free_db = _SequentialDB(
        [_FirstResult((tenant_id, True)), _ScalarResult("free")]
    )
    with (
        patch("app.modules.governance.api.v1.scim.generate_secret_blind_index", return_value="bidx"),
        patch(
            "app.modules.governance.api.v1.scim.db_session.async_session_maker",
            new=_session_maker_for(free_db),
        ),
    ):
        with pytest.raises(ScimError, match="Enterprise tier"):
            await get_scim_context(request)

    ok_db = _SequentialDB(
        [_FirstResult((tenant_id, True)), _ScalarResult("enterprise")]
    )
    ok_request = _auth_request("token-y")
    with (
        patch("app.modules.governance.api.v1.scim.generate_secret_blind_index", return_value="bidx"),
        patch(
            "app.modules.governance.api.v1.scim.db_session.async_session_maker",
            new=_session_maker_for(ok_db),
        ),
    ):
        ctx = await get_scim_context(ok_request)
    assert ctx.tenant_id == tenant_id
    assert ok_request.state.tenant_id == tenant_id


class _NestedContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class _RaceDB:
    def __init__(self, existing: object):
        self._existing = existing
        self._execute_calls = 0

    async def execute(self, _stmt: object) -> MagicMock:
        self._execute_calls += 1
        result = MagicMock()
        if self._execute_calls == 1:
            result.scalar_one_or_none.return_value = None
            return result
        result.scalar_one.return_value = self._existing
        return result

    def begin_nested(self) -> _NestedContext:
        return _NestedContext()

    def add(self, _obj: object) -> None:
        return None

    async def flush(self) -> None:
        raise IntegrityError("insert", {}, Exception("duplicate"))


@pytest.mark.asyncio
async def test_get_or_create_scim_group_race_integrity_branch() -> None:
    existing = SimpleNamespace(id=uuid4(), display_name="FinOps", display_name_norm="finops")
    race_db = _RaceDB(existing)
    group = await _get_or_create_scim_group(
        race_db, tenant_id=uuid4(), display_name="FinOps"
    )
    assert group is existing
