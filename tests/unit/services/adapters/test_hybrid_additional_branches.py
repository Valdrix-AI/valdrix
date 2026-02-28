from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.adapters.hybrid import HybridAdapter
from app.shared.core.exceptions import ExternalAPIError


class _FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        request = httpx.Request("GET", "https://example.invalid")
        response = httpx.Response(self.status_code, request=request)
        raise httpx.HTTPStatusError(
            message=f"status={self.status_code}",
            request=request,
            response=response,
        )


class _InvalidJSONResponse(_FakeResponse):
    def json(self) -> object:  # type: ignore[override]
        raise ValueError("invalid-json")


class _FakeAsyncClient:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def get(self, url: str, headers=None, params=None):  # type: ignore[no-untyped-def]
        self.calls.append({"method": "GET", "url": url, "headers": headers, "params": params})
        if not self.responses:
            raise AssertionError("No fake responses configured")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def post(self, url: str, headers=None, params=None, json=None, auth=None):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
                "auth": auth,
            }
        )
        if not self.responses:
            raise AssertionError("No fake responses configured")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _conn(
    *,
    vendor: str = "generic",
    auth_method: str = "manual",
    api_key: object | None = "token-123",
    api_secret: object | None = "secret-123",
    connector_config: dict | None = None,
    spend_feed: object | None = None,
) -> MagicMock:
    conn = MagicMock()
    conn.vendor = vendor
    conn.auth_method = auth_method
    conn.api_key = api_key
    conn.api_secret = api_secret
    conn.connector_config = connector_config or {}
    conn.spend_feed = [] if spend_feed is None else spend_feed
    return conn


def _http_status_error(status_code: int, *, method: str = "GET") -> httpx.HTTPStatusError:
    request = httpx.Request(method, "https://example.invalid")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        message=f"status={status_code}",
        request=request,
        response=response,
    )


async def _raise_external_api_error(*_args, **_kwargs):
    raise ExternalAPIError("hybrid native down")
    yield {}  # pragma: no cover


@pytest.mark.asyncio
async def test_hybrid_verify_connection_additional_native_and_manual_paths() -> None:
    manual = HybridAdapter(
        _conn(
            vendor="custom",
            auth_method="manual",
            spend_feed=[{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1.0}],
        )
    )
    assert await manual.verify_connection() is True

    ledger = HybridAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch.object(
        ledger, "_verify_ledger_http", new=AsyncMock(side_effect=ExternalAPIError("ledger down"))
    ):
        assert await ledger.verify_connection() is False
    assert "ledger down" in (ledger.last_error or "")

    vmware = HybridAdapter(_conn(vendor="vmware", auth_method="api_key"))
    with patch.object(
        vmware, "_verify_vmware", new=AsyncMock(side_effect=ExternalAPIError("vm down"))
    ):
        assert await vmware.verify_connection() is False
    assert "vm down" in (vmware.last_error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "method_name"),
    [
        ("ledger", "_stream_ledger_http_cost_and_usage"),
        ("openstack", "_stream_cloudkitty_cost_and_usage"),
        ("vmware", "_stream_vmware_cost_and_usage"),
    ],
)
async def test_hybrid_stream_fallback_for_native_vendors(vendor: str, method_name: str) -> None:
    adapter = HybridAdapter(
        _conn(
            vendor=vendor,
            auth_method="api_key",
            spend_feed=[{"timestamp": "2026-01-15T00:00:00Z", "service": "fallback", "cost_usd": 2}],
        )
    )
    with patch.object(adapter, method_name, new=_raise_external_api_error):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "hybrid_feed"
    assert "hybrid native down" in (adapter.last_error or "")


@pytest.mark.asyncio
async def test_hybrid_openstack_token_error_paths() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="openstack",
            auth_method="api_key",
            connector_config={"auth_url": "https://keystone.example.com"},
        )
    )

    bad_status = _FakeAsyncClient([_FakeResponse({}, status_code=401)])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=bad_status):
        with pytest.raises(ExternalAPIError, match="token request failed"):
            await adapter._get_openstack_token()

    missing_header = _FakeAsyncClient([_FakeResponse({}, headers={})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=missing_header):
        with pytest.raises(ExternalAPIError, match="missing X-Subject-Token"):
            await adapter._get_openstack_token()


def test_hybrid_extract_cloudkitty_summary_rows_branches() -> None:
    adapter = HybridAdapter(_conn())

    with pytest.raises(ExternalAPIError, match="invalid payload shape"):
        adapter._extract_cloudkitty_summary_rows("bad")  # type: ignore[arg-type]

    with pytest.raises(ExternalAPIError, match="missing results list"):
        adapter._extract_cloudkitty_summary_rows({"results": {}})

    rows = adapter._extract_cloudkitty_summary_rows(
        {
            "results": [
                "skip",
                {"desc": [], "qty": 1, "rate": 2},
                {"desc": ["2026-01-01"], "qty": 1, "rate": "bad"},
                {"desc": ["2026-01-01", "2026-01-31"], "qty": 2, "rate": 3},
            ]
        }
    )
    assert rows == [{"begin": "2026-01-01", "end": "2026-01-31", "qty": 2, "rate": 3}]


@pytest.mark.asyncio
async def test_hybrid_verify_and_stream_cloudkitty_conversion_fallback() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="openstack",
            auth_method="api_key",
            connector_config={
                "auth_url": "https://keystone.example.com",
                "cloudkitty_base_url": "https://cloudkitty.example.com",
                "currency": "EUR",
            },
        )
    )
    payload = {
        "results": [{"desc": ["2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z"], "qty": 2, "rate": 10}]
    }

    with (
        patch.object(adapter, "_get_openstack_token", new=AsyncMock(return_value="token-1")),
        patch.object(adapter, "_get_json", new=AsyncMock(return_value=payload)),
    ):
        await adapter._verify_cloudkitty()

    with (
        patch.object(adapter, "_get_openstack_token", new=AsyncMock(return_value="token-1")),
        patch.object(adapter, "_get_json", new=AsyncMock(return_value=payload)),
        patch(
            "app.shared.adapters.hybrid.convert_to_usd",
            new=AsyncMock(side_effect=RuntimeError("fx down")),
        ),
    ):
        rows = [
            row
            async for row in adapter._stream_cloudkitty_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]

    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 10.0
    assert rows[0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_hybrid_vmware_session_verify_and_stream_error_paths() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="vmware",
            auth_method="api_key",
            connector_config={
                "base_url": "https://vcenter.example.com",
                "cpu_hour_usd": 0.1,
                "ram_gb_hour_usd": 0.01,
            },
        )
    )

    invalid_json_client = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=invalid_json_client):
        with pytest.raises(ExternalAPIError, match="invalid JSON"):
            await adapter._get_vmware_session_id()

    missing_value_client = _FakeAsyncClient([_FakeResponse({"value": ""})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=missing_value_client):
        with pytest.raises(ExternalAPIError, match="missing session id"):
            await adapter._get_vmware_session_id()

    with (
        patch.object(adapter, "_get_vmware_session_id", new=AsyncMock(return_value="sid")),
        patch.object(adapter, "_get_json", new=AsyncMock(return_value={"value": {}})),
    ):
        with pytest.raises(ExternalAPIError, match="invalid payload shape"):
            await adapter._verify_vmware()

    with (
        patch.object(adapter, "_get_vmware_session_id", new=AsyncMock(return_value="sid")),
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "value": [
                        {"name": "vm-off", "cpu_count": 4, "memory_size_MiB": 8192, "power_state": "POWERED_OFF"},
                        {"name": "vm-zero", "cpu_count": 0, "memory_size_MiB": 0, "power_state": "POWERED_ON"},
                    ]
                }
            ),
        ),
    ):
        rows = [
            row
            async for row in adapter._stream_vmware_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 2
    assert rows[0]["usage_amount"] == 0.0
    assert rows[0]["cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_hybrid_ledger_helpers_extract_and_conversion_fallback() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={
                "base_url": "https://ledger.example.com",
                "costs_path": "api/v2/costs",
                "api_key_header": "X-Token",
            },
        )
    )
    assert adapter._resolve_ledger_http_costs_path() == "/api/v2/costs"
    assert adapter._resolve_ledger_http_headers() == {"X-Token": "token-123"}

    assert adapter._extract_ledger_records([{"x": 1}, "skip"]) == [{"x": 1}]
    assert adapter._extract_ledger_records({"records": None}) == []
    with pytest.raises(ExternalAPIError, match="missing a list of records"):
        adapter._extract_ledger_records({"records": {"bad": True}})
    with pytest.raises(ExternalAPIError, match="invalid payload shape"):
        adapter._extract_ledger_records("bad")  # type: ignore[arg-type]

    with patch.object(adapter, "_get_json", new=AsyncMock(return_value={"records": []})):
        await adapter._verify_ledger_http()

    with (
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [
                        {
                            "timestamp": "2026-01-10T00:00:00Z",
                            "system": "Hybrid Ledger",
                            "amount_raw": 50.0,
                            "currency": "EUR",
                        }
                    ]
                }
            ),
        ),
        patch(
            "app.shared.adapters.hybrid.convert_to_usd",
            new=AsyncMock(side_effect=RuntimeError("fx down")),
        ),
    ):
        rows = [
            row
            async for row in adapter._stream_ledger_http_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 50.0
    assert rows[0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_hybrid_get_json_retry_and_error_branches() -> None:
    adapter = HybridAdapter(_conn(vendor="ledger", auth_method="api_key"))

    retry_then_ok = _FakeAsyncClient([_http_status_error(500), _FakeResponse({"ok": True})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=retry_then_ok):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    non_retry = _FakeAsyncClient([_http_status_error(401)])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=non_retry):
        with pytest.raises(ExternalAPIError, match="status 401"):
            await adapter._get_json("https://example.invalid", headers={})

    bad_json = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=bad_json):
        with pytest.raises(ExternalAPIError, match="invalid JSON"):
            await adapter._get_json("https://example.invalid", headers={})

    transport_fail = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=transport_fail):
        with pytest.raises(ExternalAPIError, match="request failed"):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_hybrid_discover_and_resource_usage_defaults() -> None:
    adapter = HybridAdapter(_conn())
    assert await adapter.discover_resources("any") == []
    assert await adapter.get_resource_usage("service", "id-1") == []


@pytest.mark.asyncio
async def test_hybrid_get_resource_usage_projects_manual_feed_rows() -> None:
    now = datetime.now(timezone.utc)
    adapter = HybridAdapter(
        _conn(
            auth_method="manual",
            spend_feed=[
                {
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                    "service": "Shared Infra",
                    "resource_id": "cluster-1",
                    "usage_amount": 8,
                    "usage_unit": "node-hour",
                    "cost_usd": 12.0,
                },
                {
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "service": "Shared Infra",
                    "resource_id": "cluster-2",
                    "usage_amount": 4,
                    "cost_usd": 7.0,
                },
            ],
        )
    )
    rows = await adapter.get_resource_usage("shared", "cluster-1")
    assert len(rows) == 1
    assert rows[0]["provider"] == "hybrid"
    assert rows[0]["resource_id"] == "cluster-1"
    assert rows[0]["usage_unit"] == "node-hour"

    defaulted_unit_rows = await adapter.get_resource_usage("shared", "cluster-2")
    assert len(defaulted_unit_rows) == 1
    assert defaulted_unit_rows[0]["usage_unit"] == "unit"


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def test_hybrid_helper_resolution_branches() -> None:
    unknown_native = HybridAdapter(_conn(vendor="custom", auth_method="api_key"))
    assert unknown_native._native_vendor is None

    not_api_key = HybridAdapter(_conn(vendor="ledger", auth_method="manual"))
    assert not_api_key._native_vendor is None

    with pytest.raises(ExternalAPIError, match="Missing API token"):
        HybridAdapter(_conn(auth_method="api_key", api_key=None))._resolve_api_key()
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        HybridAdapter(_conn(auth_method="api_key", api_key=_Secret(" ")))._resolve_api_key()

    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        HybridAdapter(_conn(auth_method="api_key", api_secret=None))._resolve_api_secret()
    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        HybridAdapter(
            _conn(auth_method="api_key", api_secret=_Secret(" "))
        )._resolve_api_secret()

    assert HybridAdapter(_conn(vendor="cloudkitty", auth_method="api_key"))._native_vendor == "cloudkitty"


def test_hybrid_url_pricing_ssl_and_manual_feed_branches() -> None:
    with pytest.raises(ExternalAPIError, match="auth_url is required"):
        HybridAdapter(_conn(connector_config={}))._resolve_openstack_auth_url()
    with pytest.raises(ExternalAPIError, match="must be an http"):
        HybridAdapter(
            _conn(connector_config={"auth_url": "keystone.local"})
        )._resolve_openstack_auth_url()
    assert (
        HybridAdapter(_conn(connector_config={"auth_url": "https://keystone.example.com/v3"}))
        ._resolve_openstack_auth_url()
        .endswith("/v3/auth/tokens")
    )
    assert (
        HybridAdapter(
            _conn(
                connector_config={
                    "auth_url": "https://keystone.example.com/v3/auth/tokens"
                }
            )
        )._resolve_openstack_auth_url()
        == "https://keystone.example.com/v3/auth/tokens"
    )

    with pytest.raises(ExternalAPIError, match="cloudkitty_base_url is required"):
        HybridAdapter(_conn(connector_config={}))._resolve_cloudkitty_base_url()
    with pytest.raises(ExternalAPIError, match="must be an http"):
        HybridAdapter(
            _conn(connector_config={"cloudkitty_base_url": "ck.local"})
        )._resolve_cloudkitty_base_url()

    with pytest.raises(ExternalAPIError, match="base_url is required"):
        HybridAdapter(_conn(connector_config={}))._resolve_vmware_base_url()
    with pytest.raises(ExternalAPIError, match="must be an http"):
        HybridAdapter(_conn(connector_config={"base_url": "vc.local"}))._resolve_vmware_base_url()

    with pytest.raises(ExternalAPIError, match="cpu_hour_usd must be a positive number"):
        HybridAdapter(_conn(connector_config={"cpu_hour_usd": 0, "ram_gb_hour_usd": 0.1}))._resolve_vmware_pricing()
    with pytest.raises(ExternalAPIError, match="ram_gb_hour_usd must be a positive number"):
        HybridAdapter(_conn(connector_config={"cpu_hour_usd": 0.1, "ram_gb_hour_usd": 0}))._resolve_vmware_pricing()

    assert HybridAdapter(_conn(connector_config={"verify_ssl": False}))._resolve_verify_ssl() is False
    assert HybridAdapter(_conn(connector_config={"ssl_verify": False}))._resolve_verify_ssl() is False
    assert HybridAdapter(_conn(connector_config={}))._resolve_verify_ssl() is True

    adapter = HybridAdapter(_conn())
    assert adapter._validate_manual_feed("bad-shape") is False  # type: ignore[arg-type]
    assert "at least one record" in (adapter.last_error or "")
    assert adapter._validate_manual_feed(["bad-entry"]) is False
    assert "must be a JSON object" in (adapter.last_error or "")
    assert adapter._validate_manual_feed([{"cost_usd": 1.0}]) is False
    assert "missing timestamp/date" in (adapter.last_error or "")
    assert adapter._validate_manual_feed([{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": "x"}]) is False
    assert "must include numeric cost_usd" in (adapter.last_error or "")


@pytest.mark.asyncio
async def test_hybrid_feed_stream_non_list_and_default_value_branches() -> None:
    non_list = HybridAdapter(_conn(auth_method="manual", spend_feed={"bad": True}))
    rows = [
        row
        async for row in non_list.stream_cost_and_usage(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
    ]
    assert rows == []

    adapter = HybridAdapter(
        _conn(
            auth_method="manual",
            spend_feed=[
                {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 1.0},
                {"timestamp": "2026-01-10T00:00:00Z", "cost_usd": "bad", "tags": "bad-shape"},
            ],
        )
    )
    rows = [
        row
        async for row in adapter.stream_cost_and_usage(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
    ]
    assert len(rows) == 1
    assert rows[0]["service"] == "Hybrid Infra"
    assert rows[0]["cost_usd"] == 0.0
    assert rows[0]["tags"] == {}


@pytest.mark.asyncio
async def test_hybrid_openstack_vmware_and_ledger_success_branches() -> None:
    openstack = HybridAdapter(
        _conn(
            vendor="openstack",
            auth_method="api_key",
            connector_config={
                "auth_url": "https://keystone.example.com",
                "cloudkitty_base_url": "https://cloudkitty.example.com",
            },
        )
    )
    openstack_token_client = _FakeAsyncClient(
        [_FakeResponse({}, headers={"X-Subject-Token": " token-123 "})]
    )
    with patch(
        "app.shared.adapters.hybrid.httpx.AsyncClient",
        return_value=openstack_token_client,
    ):
        token = await openstack._get_openstack_token()
    assert token == "token-123"

    with (
        patch.object(openstack, "_get_openstack_token", new=AsyncMock(return_value="token-123")),
        patch.object(
            openstack,
            "_get_json",
            new=AsyncMock(
                return_value={"results": [{"desc": ["2026-01-01T00:00:00Z"], "qty": "n/a", "rate": 4}]}
            ),
        ),
    ):
        rows = [
            row
            async for row in openstack._stream_cloudkitty_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["usage_amount"] is None
    assert rows[0]["cost_usd"] == 4.0

    vmware = HybridAdapter(
        _conn(
            vendor="vmware",
            auth_method="api_key",
            connector_config={
                "base_url": "https://vcenter.example.com",
                "cpu_hour_usd": 0.1,
                "ram_gb_hour_usd": 0.01,
                "include_powered_off": True,
            },
        )
    )
    with (
        patch.object(vmware, "_get_vmware_session_id", new=AsyncMock(return_value="sid")),
        patch.object(
            vmware,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "value": [
                        {
                            "name": "vm-off",
                            "cpu_count": 2,
                            "memory_size_MiB": 4096,
                            "power_state": "POWERED_OFF",
                        }
                    ]
                }
            ),
        ),
    ):
        await vmware._verify_vmware()
        rows = [
            row
            async for row in vmware._stream_vmware_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 2
    assert rows[0]["usage_amount"] == 1.0
    assert rows[0]["cost_usd"] > 0.0

    ledger = HybridAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={"base_url": "https://ledger.example.com"},
        )
    )
    assert ledger._resolve_ledger_http_costs_path() == "/api/v1/finops/costs"
    assert ledger._resolve_ledger_http_headers() == {"Authorization": "Bearer token-123"}
    with (
        patch.object(
            ledger,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [
                        {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 1},
                        {
                            "timestamp": "2026-01-10T00:00:00Z",
                            "system": "Hybrid Ledger",
                            "cost_usd": 5.0,
                            "amount_raw": 5.1,
                            "resource_id": "res-1",
                            "usage_amount": 2,
                            "usage_unit": "hour",
                        },
                        {
                            "timestamp": "2026-01-11T00:00:00Z",
                            "amount_raw": 3.0,
                            "currency": "EUR",
                            "id": "",
                            "usage_amount": "bad",
                            "usage_unit": "",
                        },
                    ]
                }
            ),
        ),
        patch("app.shared.adapters.hybrid.convert_to_usd", new=AsyncMock(return_value=7.7)),
    ):
        rows = [
            row
            async for row in ledger._stream_ledger_http_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 2
    assert rows[0]["resource_id"] == "res-1"
    assert rows[0]["usage_amount"] == 2.0
    assert rows[0]["usage_unit"] == "hour"
    assert rows[1]["resource_id"] is None
    assert rows[1]["usage_amount"] is None
    assert rows[1]["usage_unit"] is None
    assert rows[1]["cost_usd"] == 7.7


@pytest.mark.asyncio
async def test_hybrid_resolution_and_get_json_unexpected_retry_exhaustion_branches() -> None:
    with pytest.raises(ExternalAPIError, match="Missing connector_config.base_url"):
        HybridAdapter(
            _conn(vendor="ledger", auth_method="api_key", connector_config={})
        )._resolve_ledger_http_base_url()
    with pytest.raises(ExternalAPIError, match="must be an http"):
        HybridAdapter(
            _conn(
                vendor="ledger",
                auth_method="api_key",
                connector_config={"base_url": "ledger.local"},
            )
        )._resolve_ledger_http_base_url()

    adapter = HybridAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch("app.shared.adapters.hybrid._NATIVE_MAX_RETRIES", 0):
        with pytest.raises(ExternalAPIError, match="failed unexpectedly"):
            await adapter._get_json("https://example.invalid", headers={})


def _single_row_gen(row: dict[str, object]):
    async def _gen(*_args, **_kwargs):
        yield row

    return _gen


def test_hybrid_month_iteration_and_cloudkitty_empty_rows() -> None:
    adapter = HybridAdapter(_conn())
    months = adapter._iter_month_starts(
        datetime(2025, 12, 15, tzinfo=timezone.utc),
        datetime(2026, 2, 2, tzinfo=timezone.utc),
    )
    assert months == [
        datetime(2025, 12, 1).date(),
        datetime(2026, 1, 1).date(),
        datetime(2026, 2, 1).date(),
    ]

    assert adapter._extract_cloudkitty_summary_rows(
        {"results": ["skip", {"desc": [], "rate": "bad"}]}
    ) == []


@pytest.mark.asyncio
async def test_hybrid_verify_connection_remaining_branches() -> None:
    unsupported_vendor = HybridAdapter(_conn(vendor="custom", auth_method="api_key"))
    assert await unsupported_vendor.verify_connection() is False
    assert "not supported for vendor" in (unsupported_vendor.last_error or "")

    unsupported_auth = HybridAdapter(_conn(vendor="ledger", auth_method="oauth"))
    assert await unsupported_auth.verify_connection() is False
    assert "must be one of" in (unsupported_auth.last_error or "")

    ledger = HybridAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch.object(ledger, "_verify_ledger_http", new=AsyncMock(return_value=None)):
        assert await ledger.verify_connection() is True

    cloudkitty = HybridAdapter(_conn(vendor="openstack", auth_method="api_key"))
    with patch.object(cloudkitty, "_verify_cloudkitty", new=AsyncMock(return_value=None)):
        assert await cloudkitty.verify_connection() is True

    with patch.object(
        cloudkitty,
        "_verify_cloudkitty",
        new=AsyncMock(side_effect=ExternalAPIError("cloudkitty down")),
    ):
        assert await cloudkitty.verify_connection() is False
    assert "cloudkitty down" in (cloudkitty.last_error or "")

    vmware = HybridAdapter(_conn(vendor="vmware", auth_method="api_key"))
    with patch.object(vmware, "_verify_vmware", new=AsyncMock(return_value=None)):
        assert await vmware.verify_connection() is True

    manual_generic = HybridAdapter(_conn(vendor="custom", auth_method="manual", spend_feed=[]))
    with patch.object(manual_generic, "_validate_manual_feed", return_value=False):
        assert await manual_generic.verify_connection() is False
    assert "missing or invalid" in (manual_generic.last_error or "").lower()


@pytest.mark.asyncio
async def test_hybrid_get_json_fallthrough_raises_last_error_branch() -> None:
    adapter = HybridAdapter(_conn(vendor="ledger", auth_method="api_key"))
    transport_fail = _FakeAsyncClient([httpx.ConnectError("c1"), httpx.ConnectError("c2")])
    with (
        patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=transport_fail),
        patch("app.shared.adapters.http_retry.range", return_value=[1, 2]),
    ):
        with pytest.raises(ExternalAPIError, match="Hybrid request failed:"):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "method_name"),
    [
        ("ledger", "_stream_ledger_http_cost_and_usage"),
        ("openstack", "_stream_cloudkitty_cost_and_usage"),
        ("vmware", "_stream_vmware_cost_and_usage"),
    ],
)
async def test_hybrid_native_stream_success_short_circuit(
    vendor: str, method_name: str
) -> None:
    adapter = HybridAdapter(_conn(vendor=vendor, auth_method="api_key", spend_feed=[]))
    expected_row = {"provider": "hybrid", "service": "native"}
    with patch.object(adapter, method_name, new=_single_row_gen(expected_row)):
        rows = [
            row
            async for row in adapter.stream_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        ]
    assert rows == [expected_row]


@pytest.mark.asyncio
async def test_hybrid_vmware_session_http_error_success_and_stream_invalid_shape() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="vmware",
            auth_method="api_key",
            connector_config={
                "base_url": "https://vcenter.example.com",
                "cpu_hour_usd": 0.1,
                "ram_gb_hour_usd": 0.01,
            },
        )
    )

    http_error_client = _FakeAsyncClient([_FakeResponse({}, status_code=401)])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=http_error_client):
        with pytest.raises(ExternalAPIError, match="session creation failed"):
            await adapter._get_vmware_session_id()

    ok_client = _FakeAsyncClient([_FakeResponse({"value": "sid-1"})])
    with patch("app.shared.adapters.hybrid.httpx.AsyncClient", return_value=ok_client):
        session_id = await adapter._get_vmware_session_id()
    assert session_id == "sid-1"

    with (
        patch.object(adapter, "_get_vmware_session_id", new=AsyncMock(return_value="sid")),
        patch.object(adapter, "_get_json", new=AsyncMock(return_value={"value": {}})),
    ):
        with pytest.raises(ExternalAPIError, match="invalid payload shape"):
            _ = [
                row
                async for row in adapter._stream_vmware_cost_and_usage(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
            ]


@pytest.mark.asyncio
async def test_hybrid_ledger_cost_path_default_and_usd_no_conversion_branch() -> None:
    adapter = HybridAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={"base_url": "https://ledger.example.com", "costs_path": 123},
        )
    )
    assert adapter._resolve_ledger_http_costs_path() == "/api/v1/finops/costs"

    convert_mock = AsyncMock(return_value=99.0)
    with (
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [
                        {
                            "timestamp": "2026-01-10T00:00:00Z",
                            "amount_raw": 5.0,
                            "currency": "USD",
                        }
                    ]
                }
            ),
        ),
        patch("app.shared.adapters.hybrid.convert_to_usd", new=convert_mock),
    ):
        rows = [
            row
            async for row in adapter._stream_ledger_http_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 5.0
    convert_mock.assert_not_called()
