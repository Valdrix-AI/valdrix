from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.saas import SaaSAdapter


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

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def get(self, url: str, headers=None, params=None):  # type: ignore[no-untyped-def]
        assert url
        _ = headers, params
        if not self.responses:
            raise AssertionError("No fake responses configured for HTTP call")
        return self.responses.pop(0)


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
