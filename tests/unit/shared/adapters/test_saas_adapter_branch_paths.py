from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest

from app.shared.adapters.saas import SaaSAdapter
from app.shared.core.credentials import SaaSCredentials
from app.shared.core.exceptions import ExternalAPIError


def _saas_credentials(**overrides: object) -> SaaSCredentials:
    base: dict[str, object] = {
        "platform": "generic",
        "auth_method": "manual",
        "connector_config": {},
        "spend_feed": [],
    }
    base.update(overrides)
    return SaaSCredentials(**base)


class _FakeAsyncClient:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None

    async def get(self, url: str, *, headers: dict[str, str], params: dict[str, object] | None = None):
        self.calls.append((url, {"headers": headers, "params": params}))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self._request = httpx.Request("GET", "https://example.invalid")
        self._response = httpx.Response(
            status_code=status_code,
            request=self._request,
            json=payload if isinstance(payload, (dict, list)) else {"value": "x"},
        )

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self._request,
                response=self._response,
            )

    def json(self) -> object:
        return self._payload


def test_saas_credential_accessor_and_property_fallback_branches() -> None:
    adapter = SaaSAdapter(MagicMock())
    assert adapter._get_credential_field("missing", default="fallback") == "fallback"

    class _SlotCreds:
        __slots__ = ("token",)

        def __init__(self) -> None:
            self.token = "abc123"

    slot_adapter = SaaSAdapter(_SlotCreds())
    assert slot_adapter._get_credential_field("token", default="fallback") == "abc123"

    adapter_none = SaaSAdapter(SimpleNamespace(some_field=None))
    assert adapter_none._get_credential_field("some_field", default="fallback") == "fallback"

    auth_adapter = SaaSAdapter(
        SimpleNamespace(auth_method=None, connector_config={"auth_method": " CSV "})
    )
    assert auth_adapter._auth_method == "csv"

    vendor_adapter = SaaSAdapter(SimpleNamespace(vendor=None, platform=" Datadog "))
    assert vendor_adapter._vendor == "datadog"

    cfg_from_extra = SaaSAdapter(
        SimpleNamespace(connector_config="not-dict", extra_config={"base_url": "https://x"})
    )
    assert cfg_from_extra._connector_config == {"base_url": "https://x"}

    cfg_empty = SaaSAdapter(
        SimpleNamespace(connector_config="not-dict", extra_config="not-dict")
    )
    assert cfg_empty._connector_config == {}


def test_saas_manual_feed_resolution_branches() -> None:
    adapter_connector_fallback = SaaSAdapter(
        SimpleNamespace(
            spend_feed=None,
            cost_feed=None,
            connector_config={"spend_feed": None, "cost_feed": [{"cost_usd": 1}]},
        )
    )
    assert adapter_connector_fallback._manual_feed == [{"cost_usd": 1}]

    adapter_none = SaaSAdapter(
        SimpleNamespace(spend_feed=None, cost_feed=None, connector_config={})
    )
    assert adapter_none._manual_feed is None


def test_saas_resolve_api_key_missing_and_blank() -> None:
    missing = SaaSAdapter(_saas_credentials(api_key=None))
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        missing._resolve_api_key()

    blank = SaaSAdapter(_saas_credentials(api_key="   "))
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        blank._resolve_api_key()


@pytest.mark.asyncio
async def test_saas_verify_connection_manual_valid_and_generic_error_message_branch() -> None:
    valid = SaaSAdapter(
        _saas_credentials(
            spend_feed=[{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1.5}]
        )
    )
    assert await valid.verify_connection() is True

    generic_error = SaaSAdapter(_saas_credentials(spend_feed=[]))
    generic_error.last_error = None
    with patch.object(generic_error, "_validate_manual_feed", return_value=False):
        assert await generic_error.verify_connection() is False
    assert generic_error.last_error == "Spend feed is missing or invalid."


@pytest.mark.asyncio
async def test_saas_verify_connection_and_stream_custom_native_vendor_fall_back_to_feed() -> None:
    feed = [{"timestamp": "2026-01-05T00:00:00Z", "cost_usd": 2.0}]
    adapter = SaaSAdapter(_saas_credentials(spend_feed=feed))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)

    with patch.object(
        SaaSAdapter, "_native_vendor", new_callable=PropertyMock, return_value="custom"
    ):
        assert await adapter.verify_connection() is True
        rows = [row async for row in adapter.stream_cost_and_usage(start, end)]

    assert len(rows) == 1
    assert rows[0]["source_adapter"] == "saas_feed"


def test_saas_validate_manual_feed_success_path_returns_true() -> None:
    adapter = SaaSAdapter(_saas_credentials())
    feed = [
        {"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1},
        {"date": "2026-01-02", "amount_usd": 2.5},
    ]
    assert adapter._validate_manual_feed(feed) is True


@pytest.mark.asyncio
async def test_saas_manual_feed_stream_skips_out_of_range_records() -> None:
    adapter = SaaSAdapter(
        _saas_credentials(
            spend_feed=[
                {"timestamp": "2025-12-01T00:00:00Z", "cost_usd": 9.0},
                {"timestamp": "2026-01-15T00:00:00Z", "cost_usd": 3.5, "service": "Ok"},
            ]
        )
    )
    rows = await adapter.get_cost_and_usage(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert rows[0]["service"] == "Ok"


@pytest.mark.asyncio
async def test_saas_verify_stripe_calls_balance_endpoint() -> None:
    adapter = SaaSAdapter(_saas_credentials(platform="stripe", auth_method="api_key", api_key="sk_live_x"))
    with patch.object(adapter, "_get_json", AsyncMock(return_value={"ok": True})) as mock_get:
        await adapter._verify_stripe()

    mock_get.assert_awaited_once()
    assert mock_get.call_args.args[0] == "https://api.stripe.com/v1/balance"


@pytest.mark.asyncio
async def test_saas_stream_stripe_branch_paths_non_dict_out_of_range_conversion_warning_and_invalid_next_token() -> None:
    adapter = SaaSAdapter(
        _saas_credentials(platform="stripe", auth_method="api_key", api_key="sk_live_x")
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    payload = {
        "data": [
            "not-a-dict",
            {
                "id": "inv-old",
                "created": int((start - timedelta(days=2)).timestamp()),
                "total": 1000,
                "currency": "usd",
            },
            {
                "id": "",
                "created": int((start + timedelta(days=1)).timestamp()),
                "total": 2500,
                "currency": "eur",
                "description": "  ",
                "customer": "cus_123",
            },
        ],
        "has_more": True,
    }

    fake_client = _FakeAsyncClient([_FakeResponse(payload)])
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch(
            "app.shared.adapters.saas.convert_to_usd",
            new=AsyncMock(side_effect=RuntimeError("fx down")),
        ),
        patch("app.shared.adapters.saas.logger.warning") as warning,
    ):
        rows = [row async for row in adapter._stream_stripe_cost_and_usage(start, end)]

    assert len(rows) == 1
    assert rows[0]["service"] == ""
    assert rows[0]["resource_id"] is None
    warning.assert_called()


@pytest.mark.asyncio
async def test_saas_stream_salesforce_missing_instance_url_raises() -> None:
    adapter = SaaSAdapter(
        _saas_credentials(platform="salesforce", auth_method="oauth", api_key="token", connector_config={})
    )
    with pytest.raises(ExternalAPIError, match="instance_url"):
        await anext(
            adapter._stream_salesforce_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        )


@pytest.mark.asyncio
async def test_saas_stream_salesforce_branch_paths_non_dict_out_of_range_conversion_warning() -> None:
    adapter = SaaSAdapter(
        _saas_credentials(
            platform="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={"instance_url": "https://example.my.salesforce.com"},
        )
    )
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 31, tzinfo=timezone.utc)
    payload = {
        "records": [
            "not-a-dict",
            {
                "Id": "old",
                "Description": "Old",
                "ServiceDate": "2025-12-31",
                "TotalPrice": "1",
                "CurrencyIsoCode": "USD",
            },
            {
                "Id": "live-1",
                "Description": None,
                "ServiceDate": "2026-01-10",
                "TotalPrice": "92.0",
                "CurrencyIsoCode": "EUR",
            },
        ]
    }
    fake_client = _FakeAsyncClient([_FakeResponse(payload)])
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch(
            "app.shared.adapters.saas.convert_to_usd",
            new=AsyncMock(side_effect=RuntimeError("fx error")),
        ),
        patch("app.shared.adapters.saas.logger.warning") as warning,
    ):
        rows = [row async for row in adapter._stream_salesforce_cost_and_usage(start, end)]

    assert len(rows) == 1
    assert rows[0]["service"] == "Salesforce Contract"
    warning.assert_called()


@pytest.mark.asyncio
async def test_saas_stream_salesforce_while_condition_false_branch() -> None:
    adapter = SaaSAdapter(
        _saas_credentials(
            platform="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={"instance_url": "https://example.my.salesforce.com"},
        )
    )

    with patch("app.shared.adapters.saas.urljoin", return_value=""):
        rows = [
            row
            async for row in adapter._stream_salesforce_cost_and_usage(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert rows == []


@pytest.mark.asyncio
async def test_saas_get_json_dead_fallback_branches_with_patched_range() -> None:
    adapter = SaaSAdapter(_saas_credentials())

    fake_client = _FakeAsyncClient([httpx.ConnectError("c1"), httpx.ConnectError("c2")])
    with (
        patch("app.shared.adapters.saas.httpx.AsyncClient", return_value=fake_client),
        patch("app.shared.adapters.saas.asyncio.sleep", new=AsyncMock()),
        patch("app.shared.adapters.saas.range", return_value=[1, 2], create=True),
    ):
        with pytest.raises(ExternalAPIError, match="c2"):
            await adapter._get_json("https://example.invalid", headers={})

    with patch("app.shared.adapters.saas.range", return_value=[], create=True):
        with pytest.raises(ExternalAPIError, match="unexpectedly"):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_saas_get_resource_usage_returns_empty_list() -> None:
    adapter = SaaSAdapter(_saas_credentials())
    assert await adapter.get_resource_usage("service", "id-1") == []
