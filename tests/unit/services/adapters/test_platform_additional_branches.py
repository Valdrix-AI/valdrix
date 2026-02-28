from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.adapters.platform import PlatformAdapter
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
    raise ExternalAPIError("native upstream down")
    yield {}  # pragma: no cover


@pytest.mark.asyncio
async def test_platform_verify_connection_additional_native_and_manual_paths() -> None:
    manual = PlatformAdapter(
        _conn(
            vendor="custom",
            auth_method="manual",
            spend_feed=[{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1.0}],
        )
    )
    assert await manual.verify_connection() is True

    ledger = PlatformAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch.object(
        ledger, "_verify_ledger_http", new=AsyncMock(side_effect=ExternalAPIError("ledger down"))
    ):
        assert await ledger.verify_connection() is False
    assert "ledger down" in (ledger.last_error or "")

    datadog = PlatformAdapter(_conn(vendor="datadog", auth_method="api_key"))
    with patch.object(
        datadog, "_verify_datadog", new=AsyncMock(side_effect=ExternalAPIError("dd down"))
    ):
        assert await datadog.verify_connection() is False
    assert "dd down" in (datadog.last_error or "")

    newrelic = PlatformAdapter(_conn(vendor="newrelic", auth_method="api_key"))
    with patch.object(
        newrelic, "_verify_newrelic", new=AsyncMock(side_effect=ExternalAPIError("nr down"))
    ):
        assert await newrelic.verify_connection() is False
    assert "nr down" in (newrelic.last_error or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "method_name"),
    [
        ("ledger", "_stream_ledger_http_cost_and_usage"),
        ("datadog", "_stream_datadog_cost_and_usage"),
        ("newrelic", "_stream_newrelic_cost_and_usage"),
    ],
)
async def test_platform_stream_fallback_for_native_vendors(vendor: str, method_name: str) -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor=vendor,
            auth_method="api_key",
            spend_feed=[{"timestamp": "2026-01-15T00:00:00Z", "service": "fallback", "cost_usd": 3}],
        )
    )
    with patch.object(adapter, method_name, new=_raise_external_api_error):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "platform_feed"
    assert "native upstream down" in (adapter.last_error or "")


def test_platform_extract_billable_usage_metrics_additional_shapes() -> None:
    adapter = PlatformAdapter(_conn())

    usage_dict = adapter._extract_billable_usage_metrics({"usage": {"hosts": 2, "bad": "x"}})
    assert usage_dict == [("hosts", 2.0, None)]

    list_with_non_dict = adapter._extract_billable_usage_metrics(
        {"usage": ["skip-me", {"metric": "hosts", "value": 4}]}
    )
    assert list_with_non_dict == [("hosts", 4.0, None)]

    top_level = adapter._extract_billable_usage_metrics({"containers": 3, "label": "ignored"})
    assert top_level == [("containers", 3.0, None)]

    with pytest.raises(ExternalAPIError, match="missing billable usage metrics"):
        adapter._extract_billable_usage_metrics({"usage": [{"metric": "", "value": "x"}]})
    with pytest.raises(ExternalAPIError, match="missing billable usage metrics"):
        adapter._extract_billable_usage_metrics("not-a-dict")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_platform_verify_datadog_and_strict_pricing_branch() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="datadog",
            auth_method="api_key",
            connector_config={"site": "datadoghq.com", "unit_prices_usd": {"hosts": 2.0}},
        )
    )
    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            return_value={"usage": [{"billing_dimension": "hosts", "usage": 1, "unit": "host"}]}
        ),
    ):
        await adapter._verify_datadog()

    strict_adapter = PlatformAdapter(
        _conn(
            vendor="datadog",
            auth_method="api_key",
            connector_config={
                "site": "datadoghq.com",
                "strict_pricing": True,
                "unit_prices_usd": {"hosts": 2.0},
            },
        )
    )
    with patch.object(
        strict_adapter,
        "_get_json",
        new=AsyncMock(return_value={"usage": [{"billing_dimension": "apm", "usage": 4}]}),
    ):
        with pytest.raises(ExternalAPIError, match="Missing unit price"):
            _ = [
                row
                async for row in strict_adapter._stream_datadog_cost_and_usage(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            ]


@pytest.mark.asyncio
async def test_platform_newrelic_helpers_and_error_paths() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="newrelic",
            auth_method="api_key",
            connector_config={
                "account_id": "123",
                "nrql_query": "SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'",
                "unit_prices_usd": {"gigabytes": 0.5},
            },
        )
    )
    assert adapter._resolve_newrelic_account_id() == 123
    assert "latest(gigabytes)" in adapter._resolve_newrelic_nrql_template()

    with patch.object(adapter, "_post_json", new=AsyncMock(return_value=[])):
        with pytest.raises(ExternalAPIError, match="invalid payload"):
            await adapter._verify_newrelic()

    with patch.object(adapter, "_post_json", new=AsyncMock(return_value={"data": "bad"})):
        with pytest.raises(ExternalAPIError, match="missing data"):
            await adapter._verify_newrelic()

    with patch.object(adapter, "_post_json", new=AsyncMock(return_value={"data": {"actor": "bad"}})):
        with pytest.raises(ExternalAPIError, match="missing actor"):
            await adapter._verify_newrelic()

    with patch.object(
        adapter,
        "_post_json",
        new=AsyncMock(return_value={"data": {"actor": {"requestContext": {}}}}),
    ):
        with pytest.raises(ExternalAPIError, match="validation failed"):
            await adapter._verify_newrelic()


@pytest.mark.asyncio
async def test_platform_stream_newrelic_invalid_shapes() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="newrelic",
            auth_method="api_key",
            connector_config={
                "account_id": 123,
                "nrql_template": "FROM X SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'",
                "unit_prices_usd": {"gigabytes": 0.5},
            },
        )
    )
    bad_payloads: list[object] = [
        [],
        {"data": None},
        {"data": {"actor": None}},
        {"data": {"actor": {"account": None}}},
        {"data": {"actor": {"account": {"nrql": None}}}},
        {"data": {"actor": {"account": {"nrql": {"results": {}}}}}},
    ]
    for payload in bad_payloads:
        with patch.object(adapter, "_post_json", new=AsyncMock(return_value=payload)):
            with pytest.raises(ExternalAPIError):
                await anext(
                    adapter._stream_newrelic_cost_and_usage(
                        datetime(2026, 1, 1, tzinfo=timezone.utc),
                        datetime(2026, 1, 31, tzinfo=timezone.utc),
                    )
                )


@pytest.mark.asyncio
async def test_platform_ledger_helpers_extract_and_conversion_fallback() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={
                "base_url": "https://ledger.example.com",
                "path": "finops/costs",
                "api_key_header": "X-API-Key",
            },
        )
    )
    assert adapter._resolve_ledger_http_costs_path() == "/finops/costs"
    assert adapter._resolve_ledger_http_headers() == {"X-API-Key": "token-123"}

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
                            "date": "2026-01-10T00:00:00Z",
                            "service": "Ledger Service",
                            "amount_raw": 92.0,
                            "currency": "EUR",
                        }
                    ]
                }
            ),
        ),
        patch(
            "app.shared.adapters.platform.convert_to_usd",
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
    assert rows[0]["cost_usd"] == 92.0
    assert rows[0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_platform_post_json_retry_and_error_branches() -> None:
    adapter = PlatformAdapter(_conn(vendor="newrelic", auth_method="api_key"))

    retry_then_ok = _FakeAsyncClient([_http_status_error(500, method="POST"), _FakeResponse({"ok": True})])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=retry_then_ok):
        payload = await adapter._post_json(
            "https://example.invalid",
            headers={"API-Key": "x"},
            json={"query": "ok"},
        )
    assert payload == {"ok": True}

    non_retry = _FakeAsyncClient([_http_status_error(401, method="POST")])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=non_retry):
        with pytest.raises(ExternalAPIError, match="failed with status 401"):
            await adapter._post_json(
                "https://example.invalid",
                headers={"API-Key": "x"},
                json={"query": "ok"},
            )

    bad_json = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=bad_json):
        with pytest.raises(ExternalAPIError, match="invalid JSON"):
            await adapter._post_json(
                "https://example.invalid",
                headers={"API-Key": "x"},
                json={"query": "ok"},
            )

    transport_fail = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=transport_fail):
        with pytest.raises(ExternalAPIError, match="request failed"):
            await adapter._post_json(
                "https://example.invalid",
                headers={"API-Key": "x"},
                json={"query": "ok"},
            )


@pytest.mark.asyncio
async def test_platform_discover_and_resource_usage_defaults() -> None:
    adapter = PlatformAdapter(_conn())
    assert await adapter.discover_resources("any") == []
    assert await adapter.get_resource_usage("service", "id-1") == []


@pytest.mark.asyncio
async def test_platform_get_resource_usage_projects_manual_feed_rows() -> None:
    now = datetime.now(timezone.utc)
    adapter = PlatformAdapter(
        _conn(
            auth_method="manual",
            spend_feed=[
                {
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                    "service": "Shared Platform",
                    "resource_id": "svc-1",
                    "usage_amount": 2,
                    "usage_unit": "unit",
                    "cost_usd": 5.0,
                },
                {
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "service": "Shared Platform",
                    "resource_id": "svc-2",
                    "usage_amount": 3,
                    "cost_usd": 9.0,
                },
            ],
        )
    )
    rows = await adapter.get_resource_usage("platform", "svc-1")
    assert len(rows) == 1
    assert rows[0]["provider"] == "platform"
    assert rows[0]["resource_id"] == "svc-1"
    assert rows[0]["usage_unit"] == "unit"

    defaulted_unit_rows = await adapter.get_resource_usage("platform", "svc-2")
    assert len(defaulted_unit_rows) == 1
    assert defaulted_unit_rows[0]["usage_unit"] == "unit"


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def test_platform_helper_resolution_branches() -> None:
    unknown_native = PlatformAdapter(_conn(vendor="custom", auth_method="api_key"))
    assert unknown_native._native_vendor is None

    not_api_key = PlatformAdapter(_conn(vendor="ledger", auth_method="manual"))
    assert not_api_key._native_vendor is None

    with pytest.raises(ExternalAPIError, match="Missing API token"):
        PlatformAdapter(_conn(auth_method="api_key", api_key=None))._resolve_api_key()
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        PlatformAdapter(
            _conn(auth_method="api_key", api_key=_Secret("   "))
        )._resolve_api_key()

    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        PlatformAdapter(_conn(auth_method="api_key", api_secret=None))._resolve_api_secret()
    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        PlatformAdapter(
            _conn(auth_method="api_key", api_secret=_Secret(" "))
        )._resolve_api_secret()

    assert (
        PlatformAdapter(_conn(vendor="new_relic", auth_method="api_key"))._native_vendor
        == "newrelic"
    )


def test_platform_url_pricing_and_ssl_resolution_branches() -> None:
    with pytest.raises(ExternalAPIError, match="api_base_url must be an http"):
        PlatformAdapter(
            _conn(vendor="datadog", connector_config={"api_base_url": "datadog.local"})
        )._resolve_datadog_base_url()

    with pytest.raises(ExternalAPIError, match="site must be a hostname"):
        PlatformAdapter(
            _conn(vendor="datadog", connector_config={"site": "bad/path"})
        )._resolve_datadog_base_url()

    assert (
        PlatformAdapter(_conn(vendor="datadog", connector_config={"site": "datadoghq.eu"}))
        ._resolve_datadog_base_url()
        .startswith("https://api.")
    )
    assert (
        PlatformAdapter(
            _conn(vendor="datadog", connector_config={"site": "https://api.datadoghq.com/"})
        )._resolve_datadog_base_url()
        == "https://api.datadoghq.com"
    )

    with pytest.raises(ExternalAPIError, match="api_base_url must be an http"):
        PlatformAdapter(
            _conn(vendor="newrelic", connector_config={"api_base_url": "newrelic.local"})
        )._resolve_newrelic_endpoint()
    assert (
        PlatformAdapter(_conn(vendor="newrelic", connector_config={}))
        ._resolve_newrelic_endpoint()
        == "https://api.newrelic.com/graphql"
    )

    with pytest.raises(ExternalAPIError, match="Missing connector_config.unit_prices_usd"):
        PlatformAdapter(_conn(connector_config={}))._resolve_unit_prices()
    with pytest.raises(ExternalAPIError, match="must contain at least one positive"):
        PlatformAdapter(
            _conn(connector_config={"unit_prices_usd": {"": 1, "x": -1}})
        )._resolve_unit_prices()

    prices = PlatformAdapter(
        _conn(connector_config={"unit_prices_usd": {"hosts": 2, "bad": "x"}})
    )._resolve_unit_prices()
    assert prices == {"hosts": 2.0}

    assert PlatformAdapter(_conn(connector_config={"verify_ssl": False}))._resolve_verify_ssl() is False
    assert PlatformAdapter(_conn(connector_config={"ssl_verify": False}))._resolve_verify_ssl() is False
    assert PlatformAdapter(_conn(connector_config={}))._resolve_verify_ssl() is True


def test_platform_manual_feed_validation_error_branches() -> None:
    adapter = PlatformAdapter(_conn())
    assert adapter._validate_manual_feed("bad-shape") is False  # type: ignore[arg-type]
    assert "at least one record" in (adapter.last_error or "")

    assert adapter._validate_manual_feed(["bad-entry"]) is False
    assert "must be a JSON object" in (adapter.last_error or "")

    assert adapter._validate_manual_feed([{"cost_usd": 1.0}]) is False
    assert "missing timestamp/date" in (adapter.last_error or "")

    assert adapter._validate_manual_feed([{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": "x"}]) is False
    assert "must include numeric cost_usd" in (adapter.last_error or "")


@pytest.mark.asyncio
async def test_platform_feed_stream_non_list_and_fallback_values() -> None:
    non_list = PlatformAdapter(_conn(auth_method="manual", spend_feed={"bad": True}))
    rows = [
        row
        async for row in non_list.stream_cost_and_usage(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
    ]
    assert rows == []

    adapter = PlatformAdapter(
        _conn(
            auth_method="manual",
            spend_feed=[
                {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 1.0},
                {
                    "timestamp": "2026-01-10T00:00:00Z",
                    "cost_usd": "nan-value",
                    "currency": "eur",
                    "tags": "bad-shape",
                },
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
    assert rows[0]["service"] == "Internal Platform"
    assert rows[0]["cost_usd"] == 0.0
    assert rows[0]["tags"] == {}
    assert rows[0]["currency"] == "EUR"


@pytest.mark.asyncio
async def test_platform_native_stream_success_rows() -> None:
    datadog = PlatformAdapter(
        _conn(
            vendor="datadog",
            auth_method="api_key",
            connector_config={"site": "datadoghq.com", "unit_prices_usd": {"hosts": 2.0}},
        )
    )
    with patch.object(
        datadog,
        "_get_json",
        new=AsyncMock(
            side_effect=[
                {"usage": [{"billing_dimension": "hosts", "usage": 3}]},
                {"usage": [{"billing_dimension": "apm", "usage": 4}]},
            ]
        ),
    ):
        rows = [
            row
            async for row in datadog._stream_datadog_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 2, 28, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 2
    assert rows[0]["cost_usd"] == 6.0
    assert rows[1]["tags"]["unpriced"] is True

    newrelic = PlatformAdapter(
        _conn(
            vendor="newrelic",
            auth_method="api_key",
            connector_config={
                "account_id": 123,
                "nrql_template": "FROM X SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'",
                "unit_prices_usd": {"gigabytes": 0.5},
            },
        )
    )
    with patch.object(
        newrelic,
        "_post_json",
        new=AsyncMock(
            return_value={
                "data": {
                    "actor": {
                        "account": {"nrql": {"results": [{"gigabytes": 8, "noise": "x"}]}}
                    }
                }
            }
        ),
    ):
        rows = [
            row
            async for row in newrelic._stream_newrelic_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 4.0


@pytest.mark.asyncio
async def test_platform_ledger_resolution_and_stream_fields() -> None:
    with pytest.raises(ExternalAPIError, match="Missing connector_config.base_url"):
        PlatformAdapter(
            _conn(vendor="ledger", auth_method="api_key", connector_config={})
        )._resolve_ledger_http_base_url()
    with pytest.raises(ExternalAPIError, match="must be an http"):
        PlatformAdapter(
            _conn(
                vendor="ledger",
                auth_method="api_key",
                connector_config={"base_url": "ledger.local"},
            )
        )._resolve_ledger_http_base_url()

    adapter = PlatformAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={"base_url": "https://ledger.example.com"},
        )
    )
    assert adapter._resolve_ledger_http_costs_path() == "/api/v1/finops/costs"
    assert adapter._resolve_ledger_http_headers() == {"Authorization": "Bearer token-123"}

    with (
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [
                        {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 1},
                        {
                            "timestamp": "2026-01-10T00:00:00Z",
                            "cost_usd": 4.5,
                            "amount_raw": 4.7,
                            "resource_id": "res-1",
                            "usage_amount": 2,
                            "usage_unit": "hour",
                            "tags": {"team": "plat"},
                        },
                        {
                            "timestamp": "2026-01-12T00:00:00Z",
                            "amount_raw": 3.0,
                            "currency": "EUR",
                            "id": "",
                            "usage_amount": "x",
                            "usage_unit": "",
                        },
                    ]
                }
            ),
        ),
        patch(
            "app.shared.adapters.platform.convert_to_usd",
            new=AsyncMock(return_value=6.6),
        ),
    ):
        rows = [
            row
            async for row in adapter._stream_ledger_http_cost_and_usage(
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
    assert rows[1]["cost_usd"] == 6.6


@pytest.mark.asyncio
async def test_platform_get_json_and_post_json_unexpected_retry_exhaustion_branch() -> None:
    adapter = PlatformAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch("app.shared.adapters.platform._NATIVE_MAX_RETRIES", 0):
        with pytest.raises(ExternalAPIError, match="failed unexpectedly"):
            await adapter._get_json("https://example.invalid", headers={})
        with pytest.raises(ExternalAPIError, match="failed unexpectedly"):
            await adapter._post_json(
                "https://example.invalid",
                headers={},
                json={},
            )


def _single_row_gen(row: dict[str, object]):
    async def _gen(*_args, **_kwargs):
        yield row

    return _gen


def test_platform_date_and_base_url_resolution_branches() -> None:
    adapter = PlatformAdapter(_conn())
    months = adapter._iter_month_starts(
        datetime(2025, 12, 15, tzinfo=timezone.utc),
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    assert months == [datetime(2025, 12, 1).date(), datetime(2026, 1, 1).date()]

    dd_api_base = PlatformAdapter(
        _conn(vendor="datadog", connector_config={"api_base_url": "https://api.dd.example.com/"})
    )
    assert dd_api_base._resolve_datadog_base_url() == "https://api.dd.example.com"

    dd_default = PlatformAdapter(_conn(vendor="datadog", connector_config={}))
    assert dd_default._resolve_datadog_base_url() == "https://api.datadoghq.com"

    nr_api_base = PlatformAdapter(
        _conn(vendor="newrelic", connector_config={"api_base_url": "https://nr.example.com/"})
    )
    assert nr_api_base._resolve_newrelic_endpoint() == "https://nr.example.com"


@pytest.mark.asyncio
async def test_platform_verify_connection_unsupported_and_native_success_paths() -> None:
    unsupported_vendor = PlatformAdapter(
        _conn(vendor="custom", auth_method="api_key", spend_feed=[])
    )
    assert await unsupported_vendor.verify_connection() is False
    assert "not supported for vendor" in (unsupported_vendor.last_error or "")

    unsupported_auth = PlatformAdapter(
        _conn(vendor="datadog", auth_method="oauth", spend_feed=[])
    )
    assert await unsupported_auth.verify_connection() is False
    assert "must be one of" in (unsupported_auth.last_error or "")

    ledger = PlatformAdapter(_conn(vendor="ledger", auth_method="api_key"))
    with patch.object(ledger, "_verify_ledger_http", new=AsyncMock(return_value=None)):
        assert await ledger.verify_connection() is True

    datadog = PlatformAdapter(_conn(vendor="datadog", auth_method="api_key"))
    with patch.object(datadog, "_verify_datadog", new=AsyncMock(return_value=None)):
        assert await datadog.verify_connection() is True

    newrelic = PlatformAdapter(_conn(vendor="newrelic", auth_method="api_key"))
    with patch.object(newrelic, "_verify_newrelic", new=AsyncMock(return_value=None)):
        assert await newrelic.verify_connection() is True

    manual_bad = PlatformAdapter(_conn(vendor="custom", auth_method="manual", spend_feed=[]))
    assert await manual_bad.verify_connection() is False
    assert "at least one record" in (manual_bad.last_error or "")

    manual_default_error = PlatformAdapter(
        _conn(vendor="custom", auth_method="manual", spend_feed=[])
    )
    with patch.object(manual_default_error, "_validate_manual_feed", return_value=False):
        assert await manual_default_error.verify_connection() is False
    assert "missing or invalid" in (manual_default_error.last_error or "").lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "method_name"),
    [
        ("ledger", "_stream_ledger_http_cost_and_usage"),
        ("datadog", "_stream_datadog_cost_and_usage"),
        ("newrelic", "_stream_newrelic_cost_and_usage"),
    ],
)
async def test_platform_stream_native_success_short_circuit(vendor: str, method_name: str) -> None:
    adapter = PlatformAdapter(_conn(vendor=vendor, auth_method="api_key", spend_feed=[]))
    expected_row = {"provider": "platform", "service": "native"}
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
async def test_platform_get_json_retry_and_error_paths() -> None:
    adapter = PlatformAdapter(_conn(vendor="ledger", auth_method="api_key"))

    retry_then_ok = _FakeAsyncClient([_http_status_error(500), _FakeResponse({"ok": True})])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=retry_then_ok):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    non_retry = _FakeAsyncClient([_http_status_error(401)])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=non_retry):
        with pytest.raises(ExternalAPIError, match="status 401"):
            await adapter._get_json("https://example.invalid", headers={})

    bad_json = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=bad_json):
        with pytest.raises(ExternalAPIError, match="invalid JSON"):
            await adapter._get_json("https://example.invalid", headers={})

    transport_fail = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=transport_fail):
        with pytest.raises(ExternalAPIError, match="request failed"):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_platform_get_json_and_post_json_fallthrough_raise_last_error() -> None:
    adapter = PlatformAdapter(_conn(vendor="ledger", auth_method="api_key"))

    get_transport_fail = _FakeAsyncClient([httpx.ConnectError("c1"), httpx.ConnectError("c2")])
    with (
        patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=get_transport_fail),
        patch("app.shared.adapters.http_retry.range", return_value=[1, 2]),
    ):
        with pytest.raises(ExternalAPIError, match="Platform request failed:"):
            await adapter._get_json("https://example.invalid", headers={})

    post_transport_fail = _FakeAsyncClient([httpx.ConnectError("p1"), httpx.ConnectError("p2")])
    with (
        patch("app.shared.adapters.platform.httpx.AsyncClient", return_value=post_transport_fail),
        patch("app.shared.adapters.http_retry.range", return_value=[1, 2]),
    ):
        with pytest.raises(ExternalAPIError, match="Platform native request failed:"):
            await adapter._post_json(
                "https://example.invalid",
                headers={"API-Key": "x"},
                json={"query": "ok"},
            )


def test_platform_newrelic_and_usage_metric_branch_edges() -> None:
    with pytest.raises(ExternalAPIError, match="requires connector_config.account_id"):
        PlatformAdapter(_conn(vendor="newrelic", connector_config={}))._resolve_newrelic_account_id()

    with pytest.raises(ExternalAPIError, match="requires connector_config.nrql_template"):
        PlatformAdapter(
            _conn(vendor="newrelic", connector_config={"account_id": 1})
        )._resolve_newrelic_nrql_template()

    adapter = PlatformAdapter(_conn())
    metrics = adapter._extract_billable_usage_metrics(
        {"usage": {"bad": "x"}, "hosts": 3}
    )
    assert metrics == [("hosts", 3.0, None)]


@pytest.mark.asyncio
async def test_platform_newrelic_verify_success_and_stream_skip_branches() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="newrelic",
            auth_method="api_key",
            connector_config={
                "account_id": 123,
                "nrql_template": "FROM X SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'",
                "unit_prices_usd": {"gigabytes": 0.5},
            },
        )
    )
    with patch.object(
        adapter,
        "_post_json",
        new=AsyncMock(
            return_value={
                "data": {"actor": {"requestContext": {"userId": "u-1"}, "account": {}}}
            }
        ),
    ):
        await adapter._verify_newrelic()

    with patch.object(
        adapter,
        "_post_json",
        new=AsyncMock(
            return_value={
                "data": {
                    "actor": {
                        "account": {
                            "nrql": {"results": ["skip", {"gigabytes": "x"}, {"gigabytes": 4}]}
                        }
                    }
                }
            }
        ),
    ):
        rows = [
            row
            async for row in adapter._stream_newrelic_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 2.0


@pytest.mark.asyncio
async def test_platform_ledger_path_and_currency_branches() -> None:
    adapter = PlatformAdapter(
        _conn(
            vendor="ledger",
            auth_method="api_key",
            connector_config={"base_url": "https://ledger.example.com", "costs_path": 123},
        )
    )
    assert adapter._resolve_ledger_http_costs_path() == "/api/v1/finops/costs"

    with (
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [
                        {"timestamp": "2026-01-10T00:00:00Z", "amount_raw": 5.0, "currency": "USD"}
                    ]
                }
            ),
        ),
        patch("app.shared.adapters.platform.convert_to_usd", new=AsyncMock(return_value=99.0)),
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
