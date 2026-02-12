from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.core.exceptions import ExternalAPIError


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

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
    def __init__(self, responses: list[_FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def get(self, url: str, headers=None, params=None):  # type: ignore[no-untyped-def]
        assert url
        self.calls.append({"url": url, "headers": headers, "params": params})
        if not self.responses:
            raise AssertionError("No fake responses configured for HTTP call")
        return self.responses.pop(0)


class _InvalidJSONResponse(_FakeResponse):
    def json(self) -> dict:  # type: ignore[override]
        raise ValueError("invalid json")


async def _raise_external_api_error(*_args, **_kwargs):
    raise ExternalAPIError("upstream down")
    yield {}  # pragma: no cover


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
                            "created": int(datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp()),
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
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "license_microsoft_graph"
    assert rows[0]["cost_usd"] == 570.0
    assert rows[0]["usage_type"] == "seat_license"


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
                            "created": int(datetime(2026, 1, 11, tzinfo=timezone.utc).timestamp()),
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
                            "created": int(datetime(2026, 1, 12, tzinfo=timezone.utc).timestamp()),
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
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 2
    assert rows[0]["cost_usd"] == 10.0
    assert rows[1]["cost_usd"] == 5.0
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
    assert rows[1]["service"] == "Contract B"


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
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=http_error_client):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    invalid_json_client = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=invalid_json_client):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    non_dict_client = _FakeAsyncClient([_FakeResponse([])])  # type: ignore[list-item]
    with patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=non_dict_client):
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
    with patch.object(adapter, "_verify_microsoft_365", new=AsyncMock(return_value=None)):
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
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client):
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
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=http_error_client):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    invalid_json_client = _FakeAsyncClient([_InvalidJSONResponse({})])
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=invalid_json_client):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    non_dict_client = _FakeAsyncClient([_FakeResponse([])])  # type: ignore[list-item]
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=non_dict_client):
        with pytest.raises(Exception):
            await adapter._get_json("https://example.invalid", headers={})

    assert await adapter.discover_resources("any") == []


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
    with patch("app.shared.adapters.license.httpx.AsyncClient", return_value=fake_client):
        payload = await adapter._get_json("https://example.invalid", headers={})

    assert payload == {"value": []}
    assert len(fake_client.calls) == 2
