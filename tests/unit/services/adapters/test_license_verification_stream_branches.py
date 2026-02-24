from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.shared.adapters.license import LicenseAdapter
from app.shared.core.exceptions import ExternalAPIError


def _conn(
    *,
    vendor: str = "generic",
    auth_method: str = "manual",
    api_key: object | None = "token-123",
    connector_config: dict | None = None,
    license_feed: object | None = None,
) -> MagicMock:
    conn = MagicMock()
    conn.vendor = vendor
    conn.auth_method = auth_method
    conn.api_key = api_key
    conn.connector_config = connector_config or {}
    conn.license_feed = [] if license_feed is None else license_feed
    return conn


class _FakeGetClient:
    def __init__(self, response: httpx.Response):
        self._response = response

    async def __aenter__(self) -> "_FakeGetClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(  # type: ignore[no-untyped-def]
        self, url: str, *, headers=None, params=None
    ) -> httpx.Response:
        return self._response


class _FakeResponse:
    def __init__(self, payload: object, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

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


class _FakeAsyncClient:
    def __init__(self, responses: list[object]):
        self.responses = list(responses)

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    async def get(self, _url: str, *, headers=None, params=None):  # type: ignore[no-untyped-def]
        _ = headers, params
        if not self.responses:
            raise AssertionError("No fake responses configured")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Secret:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _parse_or_raise(value: object) -> datetime:
    if value == "raise-me":
        raise ValueError("bad timestamp")
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_verify_connection_accepts_valid_manual_feed_and_coerce_bool_unknown_string() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="custom",
            auth_method="manual",
            license_feed=[{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": 1.0}],
        )
    )
    assert await adapter.verify_connection() is True
    assert LicenseAdapter._coerce_bool("unknown-flag") is False


@pytest.mark.asyncio
async def test_verify_connection_native_success_and_manual_last_error_preserved() -> None:
    native = LicenseAdapter(_conn(vendor="google_workspace", auth_method="oauth"))
    with patch.object(native, "_verify_native_vendor", new=AsyncMock(return_value=None)):
        assert await native.verify_connection() is True

    manual = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    def _validate_and_set_error(_feed: object) -> bool:
        manual.last_error = "custom-invalid"
        return False

    with patch.object(manual, "_validate_manual_feed", side_effect=_validate_and_set_error):
        assert await manual.verify_connection() is False
    assert manual.last_error == "custom-invalid"


def test_list_manual_feed_activity_covers_parse_exception_and_merge_branches() -> None:
    feed = [
        {"user_id": "u1", "last_active_at": "raise-me", "timestamp": "2026-01-10T00:00:00Z"},
        {"user_id": "u1", "email": "U1@example.com", "display_name": "User One"},
        {"timestamp": "2026-01-05T00:00:00Z"},
        {"user_id": "u1", "timestamp": "2026-01-01T00:00:00Z"},
    ]
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual", license_feed=feed))

    with patch("app.shared.adapters.license.parse_timestamp", side_effect=_parse_or_raise):
        rows = adapter._list_manual_feed_activity()

    assert len(rows) == 1
    assert rows[0]["email"] == "u1@example.com"
    assert rows[0]["full_name"] == "User One"
    assert rows[0]["last_active_at"] == datetime(2026, 1, 10, tzinfo=timezone.utc)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "method_name"),
    [
        ("google_workspace", "_list_google_workspace_activity"),
        ("microsoft_365", "_list_microsoft_365_activity"),
        ("github", "_list_github_activity"),
        ("slack", "_list_slack_activity"),
        ("zoom", "_list_zoom_activity"),
        ("salesforce", "_list_salesforce_activity"),
    ],
)
async def test_list_users_activity_dispatches_all_native_vendors(
    vendor: str, method_name: str
) -> None:
    adapter = LicenseAdapter(_conn(vendor=vendor, auth_method="oauth"))
    mocked = AsyncMock(return_value=[{"vendor": vendor}])
    with patch.object(adapter, method_name, new=mocked):
        rows = await adapter.list_users_activity()
    assert rows == [{"vendor": vendor}]


@pytest.mark.asyncio
async def test_verify_native_vendor_dispatches_remaining_handlers_and_unsupported() -> None:
    adapter = LicenseAdapter(_conn(vendor="slack", auth_method="oauth"))
    with (
        patch.object(adapter, "_verify_slack", new=AsyncMock()) as verify_slack,
        patch.object(adapter, "_verify_zoom", new=AsyncMock()) as verify_zoom,
        patch.object(adapter, "_verify_salesforce", new=AsyncMock()) as verify_salesforce,
    ):
        await adapter._verify_native_vendor("slack")
        await adapter._verify_native_vendor("zoom")
        await adapter._verify_native_vendor("salesforce")

    verify_slack.assert_awaited_once()
    verify_zoom.assert_awaited_once()
    verify_salesforce.assert_awaited_once()

    with pytest.raises(ExternalAPIError, match="Unsupported native license vendor"):
        await adapter._verify_native_vendor("unknown")


@pytest.mark.asyncio
async def test_verify_native_vendor_dispatches_microsoft_google_and_github() -> None:
    adapter = LicenseAdapter(_conn(vendor="google_workspace", auth_method="oauth"))
    with (
        patch.object(adapter, "_verify_microsoft_365", new=AsyncMock()) as verify_m365,
        patch.object(adapter, "_verify_google_workspace", new=AsyncMock()) as verify_google,
        patch.object(adapter, "_verify_github", new=AsyncMock()) as verify_github,
    ):
        await adapter._verify_native_vendor("microsoft_365")
        await adapter._verify_native_vendor("google_workspace")
        await adapter._verify_native_vendor("github")

    verify_m365.assert_awaited_once()
    verify_google.assert_awaited_once()
    verify_github.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_slack_zoom_and_salesforce_paths() -> None:
    slack = LicenseAdapter(_conn(vendor="slack", auth_method="oauth"))
    with patch.object(slack, "_get_json", new=AsyncMock(return_value={"ok": True})):
        await slack._verify_slack()

    with patch.object(slack, "_get_json", new=AsyncMock(return_value={"ok": False, "error": "denied"})):
        with pytest.raises(ExternalAPIError, match="Slack auth.test failed"):
            await slack._verify_slack()

    zoom = LicenseAdapter(_conn(vendor="zoom", auth_method="oauth"))
    with patch.object(zoom, "_get_json", new=AsyncMock(return_value={"id": "u1"})) as zoom_get:
        await zoom._verify_zoom()
    zoom_get.assert_awaited_once()
    assert zoom_get.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")

    salesforce = LicenseAdapter(
        _conn(
            vendor="salesforce",
            auth_method="oauth",
            connector_config={"instance_url": "https://acme.my.salesforce.com/"},
        )
    )
    with patch.object(salesforce, "_get_json", new=AsyncMock(return_value={"limits": []})) as sf_get:
        await salesforce._verify_salesforce()
    sf_url = sf_get.await_args.args[0]
    assert sf_url == "https://acme.my.salesforce.com/services/data/v60.0/limits"

    bad = LicenseAdapter(
        _conn(
            vendor="salesforce",
            auth_method="oauth",
            connector_config={"instance_url": "ftp://example.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        bad._salesforce_instance_url()


@pytest.mark.asyncio
async def test_stream_cost_and_usage_google_fallback_and_feed_window_filter() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="google_workspace",
            auth_method="oauth",
            license_feed=[
                {"timestamp": "2025-12-31T00:00:00Z", "cost_usd": 2, "service": "old"},
                {"timestamp": "2026-01-15T00:00:00Z", "cost_usd": 3, "service": "in-range"},
            ],
        )
    )

    async def _raise_google(*_: object, **__: object):  # type: ignore[no-untyped-def]
        raise ExternalAPIError("google down")
        yield {}

    with patch.object(adapter, "_stream_google_workspace_license_costs", new=_raise_google):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )

    assert len(rows) == 1
    assert rows[0]["service"] == "in-range"
    assert "google down" in (adapter.last_error or "")


@pytest.mark.asyncio
async def test_stream_cost_and_usage_microsoft_native_short_circuit() -> None:
    adapter = LicenseAdapter(
        _conn(vendor="microsoft_365", auth_method="oauth", license_feed=[{"timestamp": "2026-01-15T00:00:00Z", "cost_usd": 3}])
    )
    expected_row = {"provider": "license", "service": "native-m365"}
    with patch.object(
        adapter,
        "_stream_microsoft_365_license_costs",
        new=_row_gen(expected_row),
    ):
        rows = await adapter.get_cost_and_usage(
            start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2026, 1, 31, tzinfo=timezone.utc),
        )
    assert rows == [expected_row]


@pytest.mark.asyncio
async def test_stream_google_workspace_costs_error_and_out_of_range_branches() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="google_workspace",
            auth_method="oauth",
            connector_config={"sku_prices": {"sku-a": 12.5}},
        )
    )

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=ExternalAPIError("bad sku"))):
        with pytest.raises(ExternalAPIError, match="failed for all configured SKUs"):
            _ = [
                row
                async for row in adapter._stream_google_workspace_license_costs(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            ]

    with patch.object(adapter, "_get_json", new=AsyncMock(return_value={"totalUnits": 2})):
        rows = [
            row
            async for row in adapter._stream_google_workspace_license_costs(
                datetime(2026, 2, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]
    assert rows == []

    non_dict_prices = LicenseAdapter(
        _conn(
            vendor="google_workspace",
            auth_method="oauth",
            connector_config={"sku_prices": ["bad-shape"]},
        )
    )
    with patch.object(non_dict_prices, "_get_json", new=AsyncMock(return_value={"totalUnits": 1})):
        rows = [
            row
            async for row in non_dict_prices._stream_google_workspace_license_costs(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_stream_microsoft_costs_skips_non_dict_entries_and_out_of_range() -> None:
    adapter = LicenseAdapter(_conn(vendor="microsoft_365", auth_method="oauth"))
    payload = {
        "value": [
            "skip-me",
            {
                "skuId": "abc",
                "skuPartNumber": "M365_X",
                "consumedUnits": 7,
            },
        ]
    }

    with patch.object(adapter, "_get_json", new=AsyncMock(return_value=payload)):
        rows = [
            row
            async for row in adapter._stream_microsoft_365_license_costs(
                datetime(2026, 2, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]
    assert rows == []


@pytest.mark.asyncio
async def test_get_json_returns_empty_dict_for_204() -> None:
    adapter = LicenseAdapter(_conn())
    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(204, request=request)

    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=_FakeGetClient(response),
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {}


@pytest.mark.asyncio
async def test_activity_list_methods_handle_parse_exceptions_for_vendor_records() -> None:
    m365 = LicenseAdapter(_conn(vendor="microsoft_365", auth_method="oauth"))
    zoom = LicenseAdapter(_conn(vendor="zoom", auth_method="oauth"))
    salesforce = LicenseAdapter(
        _conn(
            vendor="salesforce",
            auth_method="oauth",
            connector_config={"instance_url": "https://acme.my.salesforce.com"},
        )
    )
    google = LicenseAdapter(_conn(vendor="google_workspace", auth_method="oauth"))

    with patch("app.shared.adapters.license.parse_timestamp", side_effect=ValueError("bad")):
        with patch.object(
            m365,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "value": [
                        {
                            "id": "u1",
                            "userPrincipalName": "user@example.com",
                            "signInActivity": {"lastSignInDateTime": "bad"},
                        }
                    ]
                }
            ),
        ):
            m365_rows = await m365._list_microsoft_365_activity()

        with patch.object(
            zoom,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "users": [{"id": "u2", "last_login_time": "bad", "status": "active"}]
                }
            ),
        ):
            zoom_rows = await zoom._list_zoom_activity()

        with patch.object(
            salesforce,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "records": [{"Id": "u3", "LastLoginDate": "bad", "Profile": {}}]
                }
            ),
        ):
            salesforce_rows = await salesforce._list_salesforce_activity()

        with patch.object(
            google,
            "_get_json",
            new=AsyncMock(
                return_value={
                    "users": [{"primaryEmail": "u4@example.com", "lastLoginTime": "bad"}]
                }
            ),
        ):
            google_rows = await google._list_google_workspace_activity()

    assert m365_rows[0]["last_active_at"] is None
    assert zoom_rows[0]["last_active_at"] is None
    assert salesforce_rows[0]["last_active_at"] is None
    assert google_rows[0]["last_active_at"] is None


@pytest.mark.asyncio
async def test_list_github_activity_handles_non_list_payload_shapes() -> None:
    adapter = LicenseAdapter(
        _conn(vendor="github", auth_method="oauth", connector_config={"github_org": "acme"})
    )
    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(side_effect=[{"members": {"bad": True}}, {"events": {"bad": True}}]),
    ):
        rows = await adapter._list_github_activity()
    assert rows == []


@pytest.mark.asyncio
async def test_list_github_activity_ignores_malformed_events_and_members() -> None:
    adapter = LicenseAdapter(
        _conn(vendor="github", auth_method="oauth", connector_config={"github_org": "acme"})
    )
    with (
        patch(
            "app.shared.adapters.license.parse_timestamp",
            side_effect=_parse_or_raise,
        ),
        patch.object(
            adapter,
            "_get_json",
            new=AsyncMock(
                side_effect=[
                    {
                        "members": [
                            "skip",
                            {"login": " "},
                            {"login": "alice", "site_admin": False},
                        ]
                    },
                    {
                        "events": [
                            "skip",
                            {"actor": "not-dict", "created_at": "2026-01-01T00:00:00Z"},
                            {"actor": {"login": "alice"}, "created_at": "raise-me"},
                            {"actor": {"login": "alice"}, "created_at": "2026-01-02T00:00:00Z"},
                        ]
                    },
                ]
            ),
        ),
    ):
        rows = await adapter._list_github_activity()

    assert len(rows) == 1
    assert rows[0]["user_id"] == "alice"
    assert rows[0]["last_active_at"] == datetime(2026, 1, 2, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_list_slack_activity_ignores_logs_without_timestamp_or_user() -> None:
    adapter = LicenseAdapter(_conn(vendor="slack", auth_method="oauth"))
    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            side_effect=[
                {
                    "ok": True,
                    "logins": [
                        {"user_id": "U1"},
                        {"date_last": 1700000000},
                    ],
                },
                {"members": [{"id": "U1", "profile": {}, "name": "Slack User"}]},
            ]
        ),
    ):
        rows = await adapter._list_slack_activity()

    assert len(rows) == 1
    assert rows[0]["user_id"] == "U1"
    assert rows[0]["last_active_at"] is None


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.invalid")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        message=f"status={status_code}",
        request=request,
        response=response,
    )


def _row_gen(row: dict[str, object]):
    async def _gen(*_args, **_kwargs):
        yield row

    return _gen


@pytest.mark.asyncio
async def test_license_helper_and_verify_connection_branch_edges() -> None:
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        LicenseAdapter(_conn(auth_method="oauth", api_key=None))._resolve_api_key()
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        LicenseAdapter(_conn(auth_method="oauth", api_key=_Secret(" ")))._resolve_api_key()

    assert LicenseAdapter(_conn(vendor="custom", auth_method="manual"))._native_vendor is None
    assert LicenseAdapter._normalize_email("not-an-email") is None
    assert LicenseAdapter._coerce_bool(1) is True
    assert LicenseAdapter._coerce_bool("yes") is True
    assert LicenseAdapter._coerce_bool("off") is False

    unsupported = LicenseAdapter(_conn(vendor="custom", auth_method="oauth"))
    assert await unsupported.verify_connection() is False
    assert "not supported for vendor" in (unsupported.last_error or "")

    native_error = LicenseAdapter(_conn(vendor="google_workspace", auth_method="oauth"))
    with patch.object(
        native_error,
        "_verify_native_vendor",
        new=AsyncMock(side_effect=ExternalAPIError("native verify failed")),
    ):
        assert await native_error.verify_connection() is False
    assert "native verify failed" in (native_error.last_error or "")

    manual_default_error = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    with patch.object(
        manual_default_error, "_validate_manual_feed", return_value=False
    ) as validate_mock:
        assert await manual_default_error.verify_connection() is False
    validate_mock.assert_called_once()
    assert "missing or invalid" in (manual_default_error.last_error or "").lower()


def test_license_manual_feed_validation_error_branches() -> None:
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    assert adapter._validate_manual_feed("bad") is False  # type: ignore[arg-type]
    assert "at least one record" in (adapter.last_error or "")

    assert adapter._validate_manual_feed(["bad-entry"]) is False
    assert "must be a JSON object" in (adapter.last_error or "")

    assert adapter._validate_manual_feed([{"cost_usd": 1.0}]) is False
    assert "missing timestamp/date" in (adapter.last_error or "")

    assert (
        adapter._validate_manual_feed(
            [{"timestamp": "2026-01-01T00:00:00Z", "cost_usd": "bad"}]
        )
        is False
    )
    assert "must include numeric cost_usd" in (adapter.last_error or "")


@pytest.mark.asyncio
async def test_license_stream_fallback_and_native_short_circuit_paths() -> None:
    m365 = LicenseAdapter(
        _conn(vendor="microsoft_365", auth_method="oauth", license_feed={"bad": True})
    )

    async def _raise_m365(*_args, **_kwargs):
        raise ExternalAPIError("m365 down")
        yield {}

    with patch.object(m365, "_stream_microsoft_365_license_costs", new=_raise_m365):
        rows = [
            row
            async for row in m365._stream_cost_and_usage_impl(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
                "DAILY",
            )
        ]
    assert rows == []
    assert "m365 down" in (m365.last_error or "")

    google = LicenseAdapter(
        _conn(vendor="google_workspace", auth_method="oauth", license_feed=[])
    )
    expected = {"provider": "license", "service": "native-google"}
    with patch.object(
        google,
        "_stream_google_workspace_license_costs",
        new=_row_gen(expected),
    ):
        rows = [
            row
            async for row in google._stream_cost_and_usage_impl(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
                "DAILY",
            )
        ]
    assert rows == [expected]


@pytest.mark.asyncio
async def test_license_verify_native_vendor_http_calls_and_stream_branches() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="google_workspace",
            auth_method="oauth",
            connector_config={
                "sku_prices": {"sku-a": 10.0, 123: 4},  # type: ignore[dict-item]
                "currency": "USD",
            },
        )
    )
    with patch.object(adapter, "_get_json", new=AsyncMock(return_value={"ok": True})) as get_mock:
        await adapter._verify_microsoft_365()
        await adapter._verify_google_workspace()
        await adapter._verify_github()
    assert get_mock.await_count == 3

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(return_value={"totalUnits": 3}),
    ):
        rows = [
            row
            async for row in adapter._stream_google_workspace_license_costs(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["usage_amount"] == 3.0

    bad_m365 = LicenseAdapter(_conn(vendor="microsoft_365", auth_method="oauth"))
    with patch.object(bad_m365, "_get_json", new=AsyncMock(return_value={"value": {}})):
        with pytest.raises(ExternalAPIError, match="Invalid Microsoft Graph"):
            _ = [
                row
                async for row in bad_m365._stream_microsoft_365_license_costs(
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 31, tzinfo=timezone.utc),
                )
            ]

    good_m365 = LicenseAdapter(
        _conn(
            vendor="microsoft_365",
            auth_method="oauth",
            connector_config={"sku_prices": {"M365_X": 5.0}},
        )
    )
    with patch.object(
        good_m365,
        "_get_json",
        new=AsyncMock(
            return_value={
                "value": [
                    {
                        "skuId": "abc",
                        "skuPartNumber": "m365_x",
                        "consumedUnits": 0,
                        "prepaidUnits": {"enabled": 2},
                    }
                ]
            }
        ),
    ):
        rows = [
            row
            async for row in good_m365._stream_microsoft_365_license_costs(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 10.0

    non_string_sku_key = LicenseAdapter(
        _conn(
            vendor="microsoft_365",
            auth_method="oauth",
            connector_config={"sku_prices": {123: 9.0, "M365_Z": 3.0}},
        )
    )
    with patch.object(
        non_string_sku_key,
        "_get_json",
        new=AsyncMock(
            return_value={
                "value": [
                    {
                        "skuId": "abc",
                        "skuPartNumber": "m365_z",
                        "consumedUnits": 1,
                    }
                ]
            }
        ),
    ):
        rows = [
            row
            async for row in non_string_sku_key._stream_microsoft_365_license_costs(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 31, tzinfo=timezone.utc),
            )
        ]
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == 3.0


@pytest.mark.asyncio
async def test_license_get_json_retry_and_shape_branches() -> None:
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="oauth"))

    list_payload_client = _FakeAsyncClient([_FakeResponse([{"id": "u1"}])])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=list_payload_client,
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"value": [{"id": "u1"}]}

    bad_shape_client = _FakeAsyncClient([_FakeResponse("bad-shape")])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=bad_shape_client,
    ):
        with pytest.raises(ExternalAPIError, match="invalid payload shape"):
            await adapter._get_json("https://example.invalid", headers={})

    retry_then_ok_client = _FakeAsyncClient(
        [_http_status_error(500), _FakeResponse({"ok": True})]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=retry_then_ok_client,
    ):
        payload = await adapter._get_json("https://example.invalid", headers={})
    assert payload == {"ok": True}

    non_retry_client = _FakeAsyncClient([_http_status_error(401)])
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=non_retry_client,
    ):
        with pytest.raises(ExternalAPIError, match="status 401"):
            await adapter._get_json("https://example.invalid", headers={})

    transport_client = _FakeAsyncClient(
        [httpx.ConnectError("c1"), httpx.ConnectError("c2"), httpx.ConnectError("c3")]
    )
    with patch(
        "app.shared.adapters.license.httpx.AsyncClient",
        return_value=transport_client,
    ):
        with pytest.raises(ExternalAPIError, match="request failed"):
            await adapter._get_json("https://example.invalid", headers={})


@pytest.mark.asyncio
async def test_license_get_json_fallthrough_raises_last_error_and_unexpected() -> None:
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="oauth"))

    fallthrough_client = _FakeAsyncClient([httpx.ConnectError("c1"), httpx.ConnectError("c2")])
    with (
        patch("app.shared.adapters.license.httpx.AsyncClient", return_value=fallthrough_client),
        patch("app.shared.adapters.license.range", return_value=[1, 2]),
    ):
        with pytest.raises(ExternalAPIError, match="License connector API request failed:"):
            await adapter._get_json("https://example.invalid", headers={})

    with patch("app.shared.adapters.license._NATIVE_MAX_RETRIES", 0):
        with pytest.raises(ExternalAPIError, match="failed unexpectedly"):
            await adapter._get_json("https://example.invalid", headers={})


def test_license_manual_activity_non_list_feed_returns_empty() -> None:
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual", license_feed={}))
    assert adapter._list_manual_feed_activity() == []
