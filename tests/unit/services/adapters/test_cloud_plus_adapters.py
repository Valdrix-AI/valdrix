from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.shared.adapters.license as license_module
import app.shared.adapters.saas as saas_module
from app.shared.adapters.hybrid import HybridAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.core.exceptions import ExternalAPIError


class _FakeResponse:
    def __init__(
        self,
        payload: dict,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = headers or {}

    def json(self) -> dict:
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


class _FakeAsyncClient:
    def __init__(self, responses: list[object]):
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def get(self, url: str, headers=None, params=None):  # type: ignore[no-untyped-def]
        assert url
        self.calls.append(
            {"method": "GET", "url": url, "headers": headers, "params": params}
        )
        if not self.responses:
            raise AssertionError("No fake responses configured for HTTP call")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item

    async def post(self, url: str, headers=None, params=None, json=None, auth=None):  # type: ignore[no-untyped-def]
        assert url
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
            raise AssertionError("No fake responses configured for HTTP call")
        next_item = self.responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


class _InvalidJSONResponse(_FakeResponse):
    def json(self) -> dict:  # type: ignore[override]
        raise ValueError("invalid json")


async def _raise_external_api_error(*_args, **_kwargs):
    raise ExternalAPIError("upstream down")
    yield {}  # pragma: no cover


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        message=f"status={status_code}",
        request=request,
        response=response,
    )


@pytest.mark.asyncio
async def test_saas_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.spend_feed = [
        {
            "date": "2026-01-10T00:00:00Z",
            "vendor": "Slack",
            "amount_usd": 25.5,
            "tags": {"team": "platform"},
        }
    ]
    adapter = SaaSAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "saas"
    assert rows[0]["service"] == "Slack"
    assert rows[0]["cost_usd"] == 25.5
    assert rows[0]["resource_id"] is None
    assert rows[0]["usage_amount"] is None
    assert rows[0]["usage_unit"] is None


@pytest.mark.asyncio
async def test_saas_adapter_native_stripe_normalizes_invoices() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_123"
    conn.spend_feed = []
    conn.connector_config = {}

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "data": [
                        {
                            "id": "in_123",
                            "created": int(
                                datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp()
                            ),
                            "amount_paid": 1299,
                            "currency": "usd",
                            "description": "Stripe Platform",
                            "customer": "cus_123",
                        }
                    ],
                    "has_more": False,
                }
            )
        ]
    )
    adapter = SaaSAdapter(conn)
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "saas_stripe_api"
    assert rows[0]["cost_usd"] == 12.99
    assert rows[0]["currency"] == "USD"
    assert rows[0]["resource_id"] == "in_123"
    assert rows[0]["usage_amount"] == 1.0
    assert rows[0]["usage_unit"] == "invoice"


@pytest.mark.asyncio
async def test_saas_adapter_native_stripe_converts_non_usd_currency() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_123"
    conn.spend_feed = []
    conn.connector_config = {}

    # 92 EUR at USD->EUR=0.92 => 100 USD
    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "data": [
                        {
                            "id": "in_234",
                            "created": int(
                                datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp()
                            ),
                            "amount_paid": 9200,
                            "currency": "eur",
                            "description": "Stripe Platform",
                            "customer": "cus_234",
                        }
                    ],
                    "has_more": False,
                }
            )
        ]
    )
    adapter = SaaSAdapter(conn)
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch(
            "app.shared.core.currency.get_exchange_rate",
            new=AsyncMock(return_value=Decimal("0.92")),
        ),
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["currency"] == "EUR"
    assert rows[0]["amount_raw"] == 92.0
    assert rows[0]["cost_usd"] == pytest.approx(100.0, abs=0.0001)
    assert rows[0]["resource_id"] == "in_234"
    assert rows[0]["usage_amount"] == 1.0
    assert rows[0]["usage_unit"] == "invoice"


@pytest.mark.asyncio
async def test_saas_adapter_native_salesforce_requires_instance_url() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "salesforce"
    conn.api_key = "token"
    conn.connector_config = {}
    conn.spend_feed = []

    adapter = SaaSAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert adapter.last_error is not None
    assert "instance_url" in adapter.last_error


@pytest.mark.asyncio
async def test_saas_adapter_native_rejects_unsupported_vendor() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "hubspot"
    conn.api_key = "token"
    conn.connector_config = {}
    conn.spend_feed = []

    adapter = SaaSAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert adapter.last_error is not None
    assert "not supported" in adapter.last_error.lower()


@pytest.mark.asyncio
async def test_saas_adapter_manual_requires_non_empty_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.spend_feed = []
    conn.connector_config = {}

    adapter = SaaSAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert "at least one record" in (adapter.last_error or "").lower()


@pytest.mark.asyncio
async def test_license_adapter_normalizes_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.license_feed = [
        {
            "timestamp": "2026-01-15T00:00:00+00:00",
            "service": "Microsoft E5",
            "cost_usd": 120.0,
        }
    ]
    adapter = LicenseAdapter(conn)
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )

    assert len(rows) == 1
    assert rows[0]["provider"] == "license"
    assert rows[0]["service"] == "Microsoft E5"
    assert rows[0]["cost_usd"] == 120.0
    assert rows[0]["resource_id"] is None
    assert rows[0]["usage_amount"] is None
    assert rows[0]["usage_unit"] is None


@pytest.mark.asyncio
async def test_license_adapter_native_microsoft_365_costs() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "microsoft_365"
    conn.api_key = "m365-token"
    conn.connector_config = {
        "default_seat_price_usd": 20,
        "sku_prices": {"SPE_E5": 57},
    }
    conn.license_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "value": [
                        {
                            "skuId": "sku-1",
                            "skuPartNumber": "SPE_E5",
                            "consumedUnits": 10,
                        }
                    ]
                }
            )
        ]
    )
    adapter = LicenseAdapter(conn)
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "license_microsoft_graph"
    assert rows[0]["cost_usd"] == 570.0
    assert rows[0]["usage_type"] == "seat_license"
    assert rows[0]["resource_id"] == "sku-1"
    assert rows[0]["usage_amount"] == 10.0
    assert rows[0]["usage_unit"] == "seat"


@pytest.mark.asyncio
async def test_license_adapter_native_rejects_unsupported_vendor() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "flexera"
    conn.api_key = "token"
    conn.connector_config = {}
    conn.license_feed = []

    adapter = LicenseAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert adapter.last_error is not None
    assert "not supported" in adapter.last_error.lower()


@pytest.mark.asyncio
async def test_license_adapter_manual_requires_non_empty_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.license_feed = []
    conn.connector_config = {}

    adapter = LicenseAdapter(conn)
    success = await adapter.verify_connection()

    assert success is False
    assert "at least one record" in (adapter.last_error or "").lower()


@pytest.mark.asyncio
async def test_saas_verify_connection_native_success_and_failure() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_12345678901234567890"
    conn.connector_config = {}

    adapter = SaaSAdapter(conn)
    with patch.object(adapter, "_verify_stripe", new=AsyncMock(return_value=None)):
        assert await adapter.verify_connection() is True

    with patch.object(
        adapter,
        "_verify_stripe",
        new=AsyncMock(side_effect=ExternalAPIError("boom")),
    ):
        assert await adapter.verify_connection() is False
        assert adapter.last_error is not None


@pytest.mark.asyncio
async def test_saas_stream_native_error_falls_back_to_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_12345678901234567890"
    conn.spend_feed = [
        {"timestamp": "2026-01-03T00:00:00Z", "service": "Fallback", "cost_usd": 5.0}
    ]
    conn.connector_config = {}

    adapter = SaaSAdapter(conn)
    with patch.object(
        adapter,
        "_stream_stripe_cost_and_usage",
        new=_raise_external_api_error,
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "saas_feed"
    assert adapter.last_error is not None


@pytest.mark.asyncio
async def test_saas_stream_stripe_pagination() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_12345678901234567890"
    conn.spend_feed = []
    conn.connector_config = {}

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "data": [
                        {
                            "id": "in_1",
                            "created": int(
                                datetime(2026, 1, 11, tzinfo=timezone.utc).timestamp()
                            ),
                            "total": 1000,
                            "currency": "usd",
                        }
                    ],
                    "has_more": True,
                }
            ),
            _FakeResponse(
                {
                    "data": [
                        {
                            "id": "in_2",
                            "created": int(
                                datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp()
                            ),
                            "amount_paid": 500,
                            "currency": "eur",
                        }
                    ],
                    "has_more": False,
                }
            ),
        ]
    )

    adapter = SaaSAdapter(conn)
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch(
            "app.shared.core.currency.get_exchange_rate",
            new=AsyncMock(return_value=Decimal("0.92")),
        ),
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 2
    assert rows[0]["cost_usd"] == 10.0
    assert rows[1]["cost_usd"] == pytest.approx(5.4347826, abs=0.0001)
    assert rows[1]["currency"] == "EUR"
    assert fake_client.calls[1]["params"]["starting_after"] == "in_1"  # type: ignore[index]


@pytest.mark.asyncio
async def test_saas_stream_salesforce_pagination() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "salesforce"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {"instance_url": "https://example.my.salesforce.com"}
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "records": [
                        {
                            "Id": "a01",
                            "Description": "Contract A",
                            "ServiceDate": "2026-01-10",
                            "TotalPrice": "12.5",
                            "CurrencyIsoCode": "usd",
                        }
                    ],
                    "nextRecordsUrl": "/services/data/v60.0/query/next",
                }
            ),
            _FakeResponse(
                {
                    "records": [
                        {
                            "Id": "a02",
                            "Description": "Contract B",
                            "ServiceDate": "2026-01-11",
                            "TotalPrice": "7.5",
                            "CurrencyIsoCode": "usd",
                        }
                    ]
                }
            ),
        ]
    )

    adapter = SaaSAdapter(conn)
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 2
    assert rows[0]["source_adapter"] == "saas_salesforce_api"


@pytest.mark.asyncio
async def test_saas_stream_salesforce_converts_non_usd_currency() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "salesforce"
    conn.api_key = "token"
    conn.connector_config = {"instance_url": "https://example.my.salesforce.com"}
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "records": [
                        {
                            "Id": "a01",
                            "Description": "Salesforce Contract",
                            "ServiceDate": "2026-01-10",
                            "TotalPrice": "92.0",
                            "CurrencyIsoCode": "eur",
                        }
                    ]
                }
            )
        ]
    )

    adapter = SaaSAdapter(conn)
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch(
            "app.shared.core.currency.get_exchange_rate",
            new=AsyncMock(return_value=Decimal("0.92")),
        ),
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["currency"] == "EUR"
    assert rows[0]["amount_raw"] == 92.0
    assert rows[0]["cost_usd"] == pytest.approx(100.0, abs=0.0001)


@pytest.mark.asyncio
async def test_saas_get_json_error_paths_and_discover_resources() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = SaaSAdapter(conn)

    http_error_client = _FakeAsyncClient(
        [
            _FakeResponse({}, status_code=500),
            _FakeResponse({}, status_code=500),
            _FakeResponse({}, status_code=500),
        ]
    )
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=http_error_client
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    invalid_json_client = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=invalid_json_client
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    non_dict_client = _FakeAsyncClient([_FakeResponse([])])  # type: ignore[list-item]
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=non_dict_client
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    assert await adapter.discover_resources("any") == []


@pytest.mark.asyncio
async def test_saas_get_json_retries_retryable_status() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = SaaSAdapter(conn)

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse({}, status_code=429),
            _FakeResponse({"data": []}, status_code=200),
        ]
    )
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        payload = await adapter._get_json("https://example.invalid", headers={})

    assert payload == {"data": []}
    assert len(fake_client.calls) == 2


@pytest.mark.asyncio
async def test_license_verify_connection_native_success_and_failure() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "microsoft_365"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {}

    adapter = LicenseAdapter(conn)
    with patch.object(
        adapter, "_verify_microsoft_365", new=AsyncMock(return_value=None)
    ):
        assert await adapter.verify_connection() is True

    with patch.object(
        adapter,
        "_verify_microsoft_365",
        new=AsyncMock(side_effect=ExternalAPIError("verify failed")),
    ):
        assert await adapter.verify_connection() is False
        assert adapter.last_error is not None


@pytest.mark.asyncio
async def test_license_stream_native_error_falls_back_to_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "microsoft_365"
    conn.api_key = "token_12345678901234567890"
    conn.license_feed = [
        {"date": "2026-01-15T00:00:00Z", "service": "Fallback", "cost_usd": 9.0}
    ]
    conn.connector_config = {}

    adapter = LicenseAdapter(conn)
    with patch.object(
        adapter,
        "_stream_microsoft_365_license_costs",
        new=_raise_external_api_error,
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "license_feed"
    assert adapter.last_error is not None


@pytest.mark.asyncio
async def test_license_native_uses_prepaid_fallback_and_default_price() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "m365"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {"default_seat_price_usd": 12.5, "currency": "usd"}
    conn.license_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "value": [
                        {
                            "skuId": "sku-x",
                            "skuPartNumber": "SKU_X",
                            "consumedUnits": 0,
                            "prepaidUnits": {"enabled": 3},
                        }
                    ]
                }
            )
        ]
    )

    adapter = LicenseAdapter(conn)
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 37.5
    assert rows[0]["currency"] == "USD"
    assert rows[0]["tags"]["consumed_units"] == 3.0


@pytest.mark.asyncio
async def test_license_get_json_error_paths_and_discover_resources() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = LicenseAdapter(conn)

    http_error_client = _FakeAsyncClient(
        [
            _FakeResponse({}, status_code=500),
            _FakeResponse({}, status_code=500),
            _FakeResponse({}, status_code=500),
        ]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=http_error_client
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    invalid_json_client = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=invalid_json_client,
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    non_dict_client = _FakeAsyncClient([_FakeResponse([])])  # type: ignore[list-item]
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=non_dict_client
    ):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    assert await adapter.discover_resources("any") == []


def test_saas_helper_branches() -> None:
    now = datetime.now(timezone.utc)
    assert saas_module.parse_timestamp(now) == now
    assert saas_module.parse_timestamp("invalid").tzinfo == timezone.utc
    assert saas_module.parse_timestamp(1700000000).tzinfo == timezone.utc
    assert saas_module.as_float(None, default=9.1) == 9.1
    assert saas_module.as_float("bad", default=3.2) == 3.2
    assert saas_module.as_float("10", divisor=0) == 10.0
    assert saas_module.is_number("12.5") is True
    assert saas_module.is_number("not-a-number") is False


def test_license_helper_branches() -> None:
    now = datetime.now(timezone.utc)
    assert license_module.parse_timestamp(now) == now
    assert license_module.parse_timestamp("invalid").tzinfo == timezone.utc
    assert license_module.parse_timestamp(1700000000).tzinfo == timezone.utc
    assert license_module.as_float(None, default=8.8) == 8.8
    assert license_module.as_float("bad", default=2.4) == 2.4
    assert license_module.is_number("12.5") is True
    assert license_module.is_number("not-a-number") is False


@pytest.mark.asyncio
async def test_saas_manual_feed_validation_error_branches() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.connector_config = {}
    adapter = SaaSAdapter(conn)

    conn.spend_feed = ["not-dict"]
    assert await adapter.verify_connection() is False
    assert "json object" in (adapter.last_error or "").lower()

    conn.spend_feed = [{"cost_usd": 1}]
    assert await adapter.verify_connection() is False
    assert "missing timestamp/date" in (adapter.last_error or "").lower()

    conn.spend_feed = [{"timestamp": "2026-01-01", "cost_usd": "x"}]
    assert await adapter.verify_connection() is False
    assert "numeric cost_usd" in (adapter.last_error or "").lower()


@pytest.mark.asyncio
async def test_license_manual_feed_validation_error_branches() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.connector_config = {}
    adapter = LicenseAdapter(conn)

    conn.license_feed = ["not-dict"]
    assert await adapter.verify_connection() is False
    assert "json object" in (adapter.last_error or "").lower()

    conn.license_feed = [{"cost_usd": 1}]
    assert await adapter.verify_connection() is False
    assert "missing timestamp/date" in (adapter.last_error or "").lower()

    conn.license_feed = [{"timestamp": "2026-01-01", "cost_usd": "x"}]
    assert await adapter.verify_connection() is False
    assert "numeric cost_usd" in (adapter.last_error or "").lower()


@pytest.mark.asyncio
async def test_saas_stream_ignores_non_list_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.spend_feed = "bad-feed"
    conn.cost_feed = "bad-feed"
    conn.connector_config = {}
    adapter = SaaSAdapter(conn)

    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )
    assert rows == []


@pytest.mark.asyncio
async def test_license_stream_ignores_non_list_feed() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    conn.license_feed = "bad-feed"
    conn.cost_feed = "bad-feed"
    conn.connector_config = {}
    adapter = LicenseAdapter(conn)

    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )
    assert rows == []


@pytest.mark.asyncio
async def test_saas_verify_salesforce_success() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "salesforce"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {"instance_url": "https://example.my.salesforce.com"}
    conn.spend_feed = []
    adapter = SaaSAdapter(conn)

    fake_client = _FakeAsyncClient([_FakeResponse({"ok": True})])
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        assert await adapter.verify_connection() is True


@pytest.mark.asyncio
async def test_saas_stream_stripe_invalid_payload_raises() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "stripe"
    conn.api_key = "sk_test_12345678901234567890"
    conn.connector_config = {}
    conn.spend_feed = []
    adapter = SaaSAdapter(conn)

    fake_client = _FakeAsyncClient([_FakeResponse({"data": {"not": "list"}})])
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(ExternalAPIError):
            await anext(
                adapter._stream_stripe_cost_and_usage(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            )


@pytest.mark.asyncio
async def test_saas_stream_salesforce_invalid_payload_raises() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "salesforce"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {"instance_url": "https://example.my.salesforce.com"}
    adapter = SaaSAdapter(conn)

    fake_client = _FakeAsyncClient([_FakeResponse({"records": {"bad": "shape"}})])
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        with pytest.raises(ExternalAPIError):
            await anext(
                adapter._stream_salesforce_cost_and_usage(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            )


@pytest.mark.asyncio
async def test_saas_get_json_retry_branches() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = SaaSAdapter(conn)

    retry_then_success = _FakeAsyncClient(
        [_http_status_error(500), _FakeResponse({"ok": True})]
    )
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=retry_then_success
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    non_retryable = _FakeAsyncClient([_http_status_error(401)])
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=non_retryable
    ):
        with pytest.raises(ExternalAPIError):
            await adapter._get_json("https://example.invalid", headers={})

    transport_retry = _FakeAsyncClient(
        [httpx.ConnectError("connect"), _FakeResponse({"ok": True})]
    )
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=transport_retry
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    transport_fail = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch(
        "app.shared.adapters.saas.httpx.AsyncClient", return_value=transport_fail
    ):
        with pytest.raises(ExternalAPIError):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_license_get_json_retry_branches() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = LicenseAdapter(conn)

    retry_then_success = _FakeAsyncClient(
        [_http_status_error(500), _FakeResponse({"ok": True})]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=retry_then_success
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    non_retryable = _FakeAsyncClient([_http_status_error(401)])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=non_retryable
    ):
        with pytest.raises(ExternalAPIError):
            await adapter._get_json("https://example.invalid", headers={})

    transport_retry = _FakeAsyncClient(
        [httpx.ConnectError("connect"), _FakeResponse({"ok": True})]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=transport_retry
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    transport_fail = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=transport_fail
    ):
        with pytest.raises(ExternalAPIError):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_license_stream_invalid_payload_raises() -> None:
    conn = MagicMock()
    conn.auth_method = "oauth"
    conn.vendor = "microsoft_365"
    conn.api_key = "token_12345678901234567890"
    conn.connector_config = {}
    adapter = LicenseAdapter(conn)

    fake_client = _FakeAsyncClient([_FakeResponse({"value": {"bad": "shape"}})])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client
    ):
        with pytest.raises(ExternalAPIError):
            await anext(
                adapter._stream_microsoft_365_license_costs(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            )


@pytest.mark.asyncio
async def test_license_get_json_retries_retryable_status() -> None:
    conn = MagicMock()
    conn.auth_method = "manual"
    conn.vendor = "generic"
    adapter = LicenseAdapter(conn)

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse({}, status_code=429),
            _FakeResponse({"value": []}, status_code=200),
        ]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})

    assert payload == {"value": []}
    assert len(fake_client.calls) == 2


@pytest.mark.asyncio
async def test_platform_adapter_native_ledger_http_normalizes_records() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "ledger_http"
    conn.api_key = "token_123"
    conn.connector_config = {
        "base_url": "https://ledger.example.com",
        "costs_path": "/api/v1/finops/costs",
    }
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "records": [
                        {
                            "timestamp": "2026-01-10T00:00:00Z",
                            "service": "Kubernetes Shared",
                            "cost_usd": 55.5,
                            "currency": "USD",
                            "tags": {"team": "platform"},
                        }
                    ]
                }
            )
        ]
    )
    adapter = PlatformAdapter(conn)
    with patch(
        "app.shared.adapters.platform.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "platform"
    assert rows[0]["service"] == "Kubernetes Shared"
    assert rows[0]["cost_usd"] == 55.5
    assert rows[0]["source_adapter"] == "platform_ledger_http"
    assert rows[0]["tags"]["team"] == "platform"
    assert fake_client.calls
    assert "start_date" in (fake_client.calls[0].get("params") or {})
    assert "end_date" in (fake_client.calls[0].get("params") or {})


@pytest.mark.asyncio
async def test_platform_adapter_native_datadog_normalizes_priced_usage() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "datadog"
    conn.api_key = "dd_api_key"
    conn.api_secret = "dd_app_key"
    conn.connector_config = {"site": "datadoghq.com", "unit_prices_usd": {"hosts": 2.0}}
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "usage": [
                        {"billing_dimension": "hosts", "usage": 3, "unit": "host"},
                    ]
                }
            )
        ]
    )

    adapter = PlatformAdapter(conn)
    with patch(
        "app.shared.adapters.platform.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "platform"
    assert rows[0]["service"] == "Datadog hosts"
    assert rows[0]["usage_amount"] == 3.0
    assert rows[0]["usage_unit"] == "host"
    assert rows[0]["cost_usd"] == 6.0
    assert rows[0]["source_adapter"] == "platform_datadog_api"


@pytest.mark.asyncio
async def test_platform_adapter_native_newrelic_normalizes_priced_nrql_results() -> (
    None
):
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "newrelic"
    conn.api_key = "nr_api_key"
    conn.connector_config = {
        "account_id": 12345,
        "nrql_template": "FROM NrMTDConsumption SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'",
        "unit_prices_usd": {"gigabytes": 0.5},
    }
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "data": {
                        "actor": {
                            "account": {
                                "nrql": {
                                    "results": [
                                        {"gigabytes": 10},
                                    ]
                                }
                            }
                        }
                    }
                }
            )
        ]
    )
    adapter = PlatformAdapter(conn)
    with patch(
        "app.shared.adapters.platform.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "platform"
    assert rows[0]["service"] == "New Relic gigabytes"
    assert rows[0]["usage_amount"] == 10.0
    assert rows[0]["cost_usd"] == 5.0
    assert rows[0]["source_adapter"] == "platform_newrelic_nerdgraph"


@pytest.mark.asyncio
async def test_hybrid_adapter_native_ledger_http_normalizes_records() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "cmdb_ledger"
    conn.api_key = "token_123"
    conn.connector_config = {"base_url": "https://ledger.example.com"}
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "data": [
                        {
                            "date": "2026-01-10T00:00:00Z",
                            "system": "VMware Cluster",
                            "amount_usd": 99.9,
                            "currency": "USD",
                            "tags": {"env": "prod"},
                        }
                    ]
                }
            )
        ]
    )
    adapter = HybridAdapter(conn)
    with patch(
        "app.shared.adapters.hybrid.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "hybrid"
    assert rows[0]["service"] == "VMware Cluster"
    assert rows[0]["cost_usd"] == 99.9
    assert rows[0]["source_adapter"] == "hybrid_ledger_http"
    assert rows[0]["tags"]["env"] == "prod"


@pytest.mark.asyncio
async def test_hybrid_adapter_native_cloudkitty_normalizes_summary() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "openstack"
    conn.api_key = "app_cred_id"
    conn.api_secret = "app_cred_secret"
    conn.connector_config = {
        "auth_url": "https://keystone.example.com",
        "cloudkitty_base_url": "https://cloudkitty.example.com",
        "currency": "USD",
        "groupby": "month",
    }
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse({}, headers={"X-Subject-Token": "token-123"}),
            _FakeResponse(
                {
                    "columns": [
                        {"name": "begin", "unit": None},
                        {"name": "end", "unit": None},
                        {"name": "qty", "unit": "GB"},
                        {"name": "rate", "unit": "USD"},
                    ],
                    "results": [
                        {
                            "desc": ["2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z"],
                            "qty": 2,
                            "rate": 10,
                        }
                    ],
                }
            ),
        ]
    )

    adapter = HybridAdapter(conn)
    with patch(
        "app.shared.adapters.hybrid.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "hybrid"
    assert rows[0]["service"] == "OpenStack CloudKitty"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["usage_amount"] == 2.0
    assert rows[0]["cost_usd"] == 10.0
    assert rows[0]["source_adapter"] == "hybrid_openstack_cloudkitty"


@pytest.mark.asyncio
async def test_hybrid_adapter_native_vmware_estimates_cost_from_inventory() -> None:
    conn = MagicMock()
    conn.auth_method = "api_key"
    conn.vendor = "vmware"
    conn.api_key = "administrator@vsphere.local"
    conn.api_secret = "password"
    conn.connector_config = {
        "base_url": "https://vcenter.example.com",
        "cpu_hour_usd": 0.1,
        "ram_gb_hour_usd": 0.01,
    }
    conn.spend_feed = []

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse({"value": "session-123"}),
            _FakeResponse(
                {
                    "value": [
                        {
                            "name": "vm-1",
                            "cpu_count": 2,
                            "memory_size_MiB": 2048,
                            "power_state": "POWERED_ON",
                        }
                    ]
                }
            ),
        ]
    )

    adapter = HybridAdapter(conn)
    with patch(
        "app.shared.adapters.hybrid.httpx.AsyncClient", return_value=fake_client
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["provider"] == "hybrid"
    assert rows[0]["service"] == "VMware vCenter (estimated)"
    assert rows[0]["usage_amount"] == 1.0
    assert rows[0]["usage_unit"] == "vm"
    # (2 vCPU * $0.1 + 2GB * $0.01) * 24h = $5.28/day
    assert rows[0]["cost_usd"] == pytest.approx(5.28, abs=0.0001)
    assert rows[0]["source_adapter"] == "hybrid_vmware_vcenter"
