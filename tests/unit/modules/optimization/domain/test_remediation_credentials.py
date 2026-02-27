from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.optimization.domain import remediation_credentials as module


class _FakeField:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: object) -> tuple[str, str, object]:  # type: ignore[override]
        return ("eq", self.name, other)

    def is_(self, other: object) -> tuple[str, str, object]:
        return ("is", self.name, other)

    def desc(self) -> tuple[str, str]:
        return ("desc", self.name)


class _FakeStatement:
    def __init__(self, model: object) -> None:
        self.model = model
        self.wheres: list[object] = []
        self.orders: list[object] = []

    def where(self, condition: object) -> "_FakeStatement":
        self.wheres.append(condition)
        return self

    def order_by(self, *clauses: object) -> "_FakeStatement":
        self.orders.extend(clauses)
        return self


def _make_model(
    *,
    status: bool = True,
    is_active: bool = False,
    last_verified_at: bool = True,
) -> type[object]:
    attrs: dict[str, object] = {
        "tenant_id": _FakeField("tenant_id"),
        "id": _FakeField("id"),
    }
    if status:
        attrs["status"] = _FakeField("status")
    if is_active:
        attrs["is_active"] = _FakeField("is_active")
    if last_verified_at:
        attrs["last_verified_at"] = _FakeField("last_verified_at")
    return type("FakeConnectionModel", (), attrs)


def _service_for(connection: object | None, *, fallback: dict[str, object] | None = None):
    return SimpleNamespace(
        credentials=fallback if fallback is not None else {"fallback": "cred"},
        db=SimpleNamespace(execute=AsyncMock(return_value="db-result")),
        _scalar_one_or_none=AsyncMock(return_value=connection),
    )


async def _invoke(
    *,
    provider: object,
    connection: object | None = None,
    tenant_id: object = "tenant-1",
    connection_id: object | None = None,
    model: type[object] | None = None,
    fallback: dict[str, object] | None = None,
    normalized_provider: str | None = None,
) -> tuple[dict[str, object], SimpleNamespace, list[_FakeStatement]]:
    statements: list[_FakeStatement] = []

    def _fake_select(model_obj: object) -> _FakeStatement:
        stmt = _FakeStatement(model_obj)
        statements.append(stmt)
        return stmt

    service = _service_for(connection, fallback=fallback)
    request = SimpleNamespace(
        provider=provider,
        tenant_id=tenant_id,
        connection_id=connection_id,
    )
    patched_model = model if model is not None else _make_model()

    with (
        patch.object(module, "select", side_effect=_fake_select),
        patch.object(module, "get_connection_model", return_value=patched_model),
        patch.object(module, "resolve_connection_region", return_value="us-test-1"),
        patch.object(
            module,
            "normalize_provider",
            return_value=provider if normalized_provider is None else normalized_provider,
        ),
    ):
        result = await module.resolve_connection_credentials(service, request)

    return result, service, statements


@pytest.mark.asyncio
async def test_resolve_connection_credentials_returns_fallback_for_missing_tenant() -> None:
    service = _service_for(connection=None, fallback={"f": "v"})
    request = SimpleNamespace(provider="aws", tenant_id=None, connection_id=None)

    with patch.object(module, "normalize_provider", return_value="aws"):
        result = await module.resolve_connection_credentials(service, request)

    assert result == {"f": "v"}
    service.db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_connection_credentials_returns_fallback_for_missing_provider() -> None:
    service = _service_for(connection=None)
    request = SimpleNamespace(provider="unknown", tenant_id="tenant-1", connection_id=None)

    with patch.object(module, "normalize_provider", return_value=None):
        result = await module.resolve_connection_credentials(service, request)

    assert result == {"fallback": "cred"}
    service.db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_connection_credentials_returns_fallback_when_model_missing() -> None:
    service = _service_for(connection=None)
    request = SimpleNamespace(provider="aws", tenant_id="tenant-1", connection_id=None)

    with (
        patch.object(module, "normalize_provider", return_value="aws"),
        patch.object(module, "get_connection_model", return_value=None),
    ):
        result = await module.resolve_connection_credentials(service, request)

    assert result == {"fallback": "cred"}
    service.db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connection_id", "expected", "uses_ordering"),
    [
        (None, {"fallback": "cred"}, True),
        ("conn-1", {}, False),
    ],
)
async def test_resolve_connection_credentials_missing_connection_result_shape(
    connection_id: str | None,
    expected: dict[str, object],
    uses_ordering: bool,
) -> None:
    result, service, statements = await _invoke(
        provider="aws",
        connection=None,
        connection_id=connection_id,
        model=_make_model(status=True, last_verified_at=True),
    )

    assert result == expected
    service.db.execute.assert_awaited_once()
    service._scalar_one_or_none.assert_awaited_once_with("db-result")
    stmt = statements[0]
    if uses_ordering:
        assert ("eq", "status", "active") in stmt.wheres
        assert ("desc", "last_verified_at") in stmt.orders
        assert ("desc", "id") in stmt.orders
    else:
        assert ("eq", "id", "conn-1") in stmt.wheres
        assert stmt.orders == []


@pytest.mark.asyncio
async def test_resolve_connection_credentials_uses_is_active_branch_without_last_verified() -> None:
    result, _service, statements = await _invoke(
        provider="aws",
        connection=None,
        model=_make_model(status=False, is_active=True, last_verified_at=False),
    )

    assert result == {"fallback": "cred"}
    stmt = statements[0]
    assert ("is", "is_active", True) in stmt.wheres
    assert stmt.orders == [("desc", "id")]


@pytest.mark.asyncio
async def test_resolve_connection_credentials_skips_status_filters_when_model_has_no_status_flags() -> None:
    result, _service, statements = await _invoke(
        provider="aws",
        connection=None,
        model=_make_model(status=False, is_active=False, last_verified_at=False),
    )

    assert result == {"fallback": "cred"}
    stmt = statements[0]
    assert ("eq", "status", "active") not in stmt.wheres
    assert all(cond[:2] != ("is", "is_active") for cond in stmt.wheres if isinstance(cond, tuple))
    assert stmt.orders == [("desc", "id")]


@pytest.mark.asyncio
async def test_resolve_connection_credentials_aws_success_and_missing_fields() -> None:
    ok_connection = SimpleNamespace(id="aws-1", role_arn="arn:aws:iam::1:role/test", external_id="ext")
    result, _service, _statements = await _invoke(provider="aws", connection=ok_connection)
    assert result == {
        "role_arn": "arn:aws:iam::1:role/test",
        "external_id": "ext",
        "region": "us-test-1",
        "connection_id": "aws-1",
    }

    missing_connection = SimpleNamespace(id="aws-2", role_arn=None, external_id="ext")
    result_missing, _service, _statements = await _invoke(
        provider="aws",
        connection=missing_connection,
        connection_id="explicit-conn",
    )
    assert result_missing == {}


@pytest.mark.asyncio
async def test_resolve_connection_credentials_azure_success_and_missing_fields() -> None:
    ok_connection = SimpleNamespace(
        id="az-1",
        azure_tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        subscription_id="sub",
    )
    result, _service, _statements = await _invoke(provider="azure", connection=ok_connection)
    assert result == {
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": "secret",
        "subscription_id": "sub",
        "region": "us-test-1",
        "connection_id": "az-1",
    }

    missing_connection = SimpleNamespace(
        id="az-2",
        azure_tenant_id="tenant",
        client_id=None,
        client_secret="secret",
        subscription_id="sub",
    )
    result_missing, _service, _statements = await _invoke(
        provider="azure",
        connection=missing_connection,
        connection_id="az-2",
    )
    assert result_missing == {}


@pytest.mark.asyncio
async def test_resolve_connection_credentials_gcp_dict_payload_and_blank_string_fallback() -> None:
    dict_connection = SimpleNamespace(
        id="gcp-1",
        service_account_json={"type": "service_account", "project_id": "proj"},
    )
    result, _service, _statements = await _invoke(provider="gcp", connection=dict_connection)
    assert result == {
        "type": "service_account",
        "project_id": "proj",
        "connection_id": "gcp-1",
        "region": "us-test-1",
    }

    blank_connection = SimpleNamespace(id="gcp-2", service_account_json="   ")
    result_blank, _service, _statements = await _invoke(provider="gcp", connection=blank_connection)
    assert result_blank == {"fallback": "cred"}


@pytest.mark.asyncio
async def test_resolve_connection_credentials_gcp_json_string_dict_and_nondict() -> None:
    json_dict_connection = SimpleNamespace(
        id="gcp-3",
        service_account_json=json.dumps({"client_email": "bot@example.com"}),
    )
    result, _service, _statements = await _invoke(provider="gcp", connection=json_dict_connection)
    assert result == {
        "client_email": "bot@example.com",
        "connection_id": "gcp-3",
        "region": "us-test-1",
    }

    json_list_connection = SimpleNamespace(id="gcp-4", service_account_json='["not-a-dict"]')
    result_list, _service, _statements = await _invoke(provider="gcp", connection=json_list_connection)
    assert result_list == {"fallback": "cred"}


@pytest.mark.asyncio
async def test_resolve_connection_credentials_gcp_invalid_json_logs_warning() -> None:
    bad_connection = SimpleNamespace(id="gcp-5", service_account_json="{bad-json")

    with patch.object(module.logger, "warning") as warning:
        result, _service, _statements = await _invoke(provider="gcp", connection=bad_connection)

    assert result == {"fallback": "cred"}
    warning.assert_called_once()
    assert warning.call_args.args[0] == "remediation_invalid_gcp_service_account_json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "feed_field", "feed_key", "includes_api_secret"),
    [
        ("saas", "spend_feed", "spend_feed", False),
        ("license", "license_feed", "license_feed", False),
        ("platform", "spend_feed", "spend_feed", True),
        ("hybrid", "spend_feed", "spend_feed", True),
    ],
)
async def test_resolve_connection_credentials_connector_providers(
    provider: str,
    feed_field: str,
    feed_key: str,
    includes_api_secret: bool,
) -> None:
    connection = SimpleNamespace(
        id=f"{provider}-1",
        vendor=f"{provider}-vendor",
        auth_method="api_key",
        api_key="key",
        api_secret="secret",
        connector_config={"enabled": True} if provider != "license" else "not-a-dict",
        spend_feed=["a", "b"],
        license_feed=["lic-a"] if provider != "license" else {"unexpected": True},
    )

    result, _service, _statements = await _invoke(provider=provider, connection=connection)

    assert result["vendor"] == f"{provider}-vendor"
    assert result["auth_method"] == "api_key"
    assert result["api_key"] == "key"
    assert result["connection_id"] == f"{provider}-1"
    assert result["region"] == "us-test-1"
    if includes_api_secret:
        assert result["api_secret"] == "secret"
    else:
        assert "api_secret" not in result

    if provider == "license":
        assert result["connector_config"] == {}
        assert result[feed_key] == []
    else:
        assert result["connector_config"] == {"enabled": True}
        assert result[feed_key]


@pytest.mark.asyncio
async def test_resolve_connection_credentials_unknown_provider_returns_fallback_after_lookup() -> None:
    connection = SimpleNamespace(id="mystery-1")
    fallback = {"x": "y"}
    result, _service, _statements = await _invoke(
        provider="ignored",
        normalized_provider="mystery",
        connection=connection,
        fallback=fallback,
    )
    assert result == fallback
