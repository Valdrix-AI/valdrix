from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import pytest

import app.shared.adapters.license_native_dispatch as native_dispatch
import app.shared.adapters.license_vendor_github as vendor_github
import app.shared.adapters.license_vendor_google as vendor_google
import app.shared.adapters.license_vendor_microsoft as vendor_microsoft
import app.shared.adapters.license_vendor_salesforce as vendor_salesforce
import app.shared.adapters.license_vendor_slack as vendor_slack
import app.shared.adapters.license_vendor_zoom as vendor_zoom
from app.shared.adapters.feed_utils import parse_timestamp
from app.shared.adapters.license import LicenseAdapter
from app.shared.core.exceptions import ExternalAPIError, UnsupportedVendorError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _SequenceClient:
    def __init__(self, responses: list[object]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict | None]] = []

    def _next(self) -> _FakeResponse:
        if not self._responses:
            raise AssertionError("No fake responses configured")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, _FakeResponse)
        return item

    async def delete(self, url: str, *, headers=None):  # type: ignore[no-untyped-def]
        self.calls.append(("DELETE", url, None))
        return self._next()

    async def post(self, url: str, *, headers=None, json=None):  # type: ignore[no-untyped-def]
        self.calls.append(("POST", url, json))
        return self._next()

    async def patch(self, url: str, *, headers=None, json=None):  # type: ignore[no-untyped-def]
        self.calls.append(("PATCH", url, json))
        return self._next()


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vendor", "expects_sku"),
    [
        ("google_workspace", True),
        ("microsoft_365", True),
        ("github", False),
        ("slack", False),
        ("zoom", False),
        ("salesforce", False),
    ],
)
async def test_revoke_license_dispatches_to_vendor_handlers(
    vendor: str, expects_sku: bool
) -> None:
    adapter = LicenseAdapter(_conn(vendor=vendor, auth_method="oauth"))
    mocked = AsyncMock(return_value=True)
    if expects_sku:
        patch_target = native_dispatch._REVOKE_WITH_SKU_FN_BY_VENDOR
    else:
        patch_target = native_dispatch._REVOKE_NO_SKU_FN_BY_VENDOR

    with patch.dict(patch_target, {vendor: mocked}, clear=False):
        result = await adapter.revoke_license("user-1", "sku-1")

    assert result is True
    if expects_sku:
        mocked.assert_awaited_once_with(adapter, "user-1", "sku-1")
    else:
        mocked.assert_awaited_once_with(adapter, "user-1")


@pytest.mark.asyncio
async def test_revoke_license_unsupported_vendor_raises() -> None:
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    with pytest.raises(UnsupportedVendorError, match="not supported"):
        await adapter.revoke_license("user-1")


@pytest.mark.asyncio
async def test_list_users_activity_dispatches_manual_native_and_unknown_vendor() -> None:
    manual_adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    with patch.object(
        manual_adapter, "_list_manual_feed_activity", return_value=[{"user_id": "m"}]
    ) as manual_mock:
        assert await manual_adapter.list_users_activity() == [{"user_id": "m"}]
    manual_mock.assert_called_once()

    m365_adapter = LicenseAdapter(_conn(vendor="microsoft_365", auth_method="oauth"))
    m365_mock = AsyncMock(return_value=[{"user_id": "ms"}])
    with patch.dict(
        native_dispatch._ACTIVITY_FN_BY_VENDOR,
        {"microsoft_365": m365_mock},
        clear=False,
    ):
        assert await m365_adapter.list_users_activity() == [{"user_id": "ms"}]
    m365_mock.assert_awaited_once_with(m365_adapter)

    unknown_adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual"))
    with patch.object(
        LicenseAdapter, "_native_vendor", new_callable=PropertyMock, return_value="mystery"
    ):
        assert await unknown_adapter.list_users_activity() == []


@pytest.mark.asyncio
async def test_list_users_activity_fail_closed_for_unsupported_native_auth_vendor() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="custom",
            auth_method="oauth",
            license_feed=[{"user_id": "u1", "timestamp": "2026-01-01T00:00:00Z"}],
        )
    )

    rows = await adapter.list_users_activity()
    assert rows == []
    assert "not supported for vendor" in str(adapter.last_error or "")


def test_list_manual_feed_activity_consolidates_latest_records() -> None:
    feed = [
        "skip",
        {
            "user_id": "alice@example.com",
            "email": "alice@example.com",
            "timestamp": "2026-01-01T00:00:00Z",
            "role": "member",
            "status": "active",
            "name": "Alice 1",
        },
        {
            "principal_id": "alice@example.com",
            "last_login_at": "2026-01-03T00:00:00Z",
            "is_admin": True,
            "suspended": False,
            "display_name": "Alice 2",
        },
        {
            "resource_id": "u-2",
            "email": "bob@example.com",
            "last_seen_at": "2026-01-02T00:00:00Z",
            "inactive": True,
            "role": "owner",
        },
        {"id": "u-3", "email": "bad@example.com", "timestamp": "not-a-date"},
    ]
    adapter = LicenseAdapter(_conn(vendor="custom", auth_method="manual", license_feed=feed))

    rows = adapter._list_manual_feed_activity()
    by_id = {row["user_id"]: row for row in rows}

    assert "alice@example.com" in by_id
    assert by_id["alice@example.com"]["is_admin"] is True
    assert by_id["alice@example.com"]["full_name"] == "Alice 1"
    assert by_id["alice@example.com"]["last_active_at"] == datetime(
        2026, 1, 3, tzinfo=timezone.utc
    )

    assert by_id["u-2"]["suspended"] is True
    assert by_id["u-2"]["is_admin"] is True
    assert by_id["u-2"]["email"] == "bob@example.com"
    assert isinstance(by_id["u-3"]["last_active_at"], datetime)


@pytest.mark.asyncio
async def test_revoke_google_workspace_handles_success_and_failures() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="google_workspace",
            auth_method="oauth",
            connector_config={"managed_skus": ["sku-a", "sku-b"]},
        )
    )

    success_client = _SequenceClient([_FakeResponse(404), _FakeResponse(204)])
    with patch("app.shared.core.http.get_http_client", return_value=success_client):
        assert await vendor_google.revoke_google_workspace(adapter, "user@example.com") is True
    assert len(success_client.calls) == 2

    fail_client = _SequenceClient([_FakeResponse(500)])
    with patch("app.shared.core.http.get_http_client", return_value=fail_client):
        assert await vendor_google.revoke_google_workspace(adapter, "user@example.com", "sku-a") is False

    error_client = _SequenceClient([httpx.ConnectError("boom"), _FakeResponse(404)])
    with patch("app.shared.core.http.get_http_client", return_value=error_client):
        assert await vendor_google.revoke_google_workspace(adapter, "user@example.com", "sku-a") is False


@pytest.mark.asyncio
async def test_revoke_microsoft_365_branch_paths() -> None:
    adapter = LicenseAdapter(_conn(vendor="microsoft_365", auth_method="oauth"))
    assert await vendor_microsoft.revoke_microsoft_365(adapter, "user", None) is False

    ok_client = _SequenceClient([_FakeResponse(200)])
    with patch("app.shared.core.http.get_http_client", return_value=ok_client):
        assert await vendor_microsoft.revoke_microsoft_365(adapter, "user", "sku-1") is True
    assert ok_client.calls[0][2] == {"addLicenses": [], "removeLicenses": ["sku-1"]}

    bad_client = _SequenceClient([_FakeResponse(500)])
    with patch("app.shared.core.http.get_http_client", return_value=bad_client):
        assert await vendor_microsoft.revoke_microsoft_365(adapter, "user", "sku-1") is False

    err_client = _SequenceClient([httpx.ConnectError("down")])
    with patch("app.shared.core.http.get_http_client", return_value=err_client):
        assert await vendor_microsoft.revoke_microsoft_365(adapter, "user", "sku-1") is False


@pytest.mark.asyncio
async def test_list_microsoft_365_activity_parses_and_handles_errors() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="microsoft_365",
            auth_method="oauth",
            connector_config={"admin_upns": ["admin@example.com"]},
        )
    )
    payload = {
        "value": [
            {
                "id": "u1",
                "userPrincipalName": "admin@example.com",
                "displayName": "Admin",
                "accountEnabled": True,
                "signInActivity": {"lastSuccessfulSignInDateTime": "2026-01-10T00:00:00Z"},
            },
            {
                "id": "u2",
                "userPrincipalName": "member@example.com",
                "displayName": "Member",
                "accountEnabled": False,
                "signInActivity": {"lastSignInDateTime": "bad-date"},
            },
            {
                "id": "u3",
                "userPrincipalName": "nolast@example.com",
                "displayName": "No Last",
                "accountEnabled": True,
                "signInActivity": {},
            },
        ]
    }

    with patch.object(adapter, "_get_json", new=AsyncMock(return_value=payload)):
        rows = await vendor_microsoft.list_microsoft_365_activity(adapter, parse_timestamp_fn=parse_timestamp)
    assert len(rows) == 3
    assert rows[0]["is_admin"] is True
    assert rows[0]["last_active_at"] == datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert rows[1]["suspended"] is True
    assert isinstance(rows[1]["last_active_at"], datetime)
    assert rows[2]["last_active_at"] is None

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_microsoft.list_microsoft_365_activity(adapter, parse_timestamp_fn=parse_timestamp) == []


@pytest.mark.asyncio
async def test_github_revoke_and_activity_paths() -> None:
    adapter = LicenseAdapter(
        _conn(vendor="github", auth_method="oauth", connector_config={"github_org": "acme"})
    )

    ok_client = _SequenceClient([_FakeResponse(204)])
    with patch("app.shared.core.http.get_http_client", return_value=ok_client):
        assert await vendor_github.revoke_github(adapter, "alice") is True

    bad_client = _SequenceClient([_FakeResponse(500)])
    with patch("app.shared.core.http.get_http_client", return_value=bad_client):
        assert await vendor_github.revoke_github(adapter, "alice") is False

    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([httpx.ConnectError("x")])):
        assert await vendor_github.revoke_github(adapter, "alice") is False

    no_org = LicenseAdapter(_conn(vendor="github", auth_method="oauth", connector_config={}))
    assert await vendor_github.revoke_github(no_org, "alice") is False
    assert await vendor_github.list_github_activity(no_org, parse_timestamp_fn=parse_timestamp) == []

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            side_effect=[
                {"members": [{"login": "alice", "site_admin": True, "name": "Alice"}]},
                {
                    "events": [
                        {"actor": {"login": "alice"}, "created_at": "2026-01-11T00:00:00Z"},
                        {"actor": {"login": "alice"}, "created_at": "2026-01-10T00:00:00Z"},
                        {"actor": {"login": "alice"}, "created_at": "bad"},
                    ]
                },
            ]
        ),
    ):
        rows = await vendor_github.list_github_activity(adapter, parse_timestamp_fn=parse_timestamp)
    assert rows[0]["user_id"] == "alice"
    assert rows[0]["is_admin"] is True
    assert isinstance(rows[0]["last_active_at"], datetime)

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_github.list_github_activity(adapter, parse_timestamp_fn=parse_timestamp) == []


@pytest.mark.asyncio
async def test_zoom_revoke_and_activity_paths() -> None:
    adapter = LicenseAdapter(_conn(vendor="zoom", auth_method="oauth"))

    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([_FakeResponse(204)])):
        assert await vendor_zoom.revoke_zoom(adapter, "u1") is True
    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([_FakeResponse(400)])):
        assert await vendor_zoom.revoke_zoom(adapter, "u1") is False
    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([httpx.ConnectError("x")])):
        assert await vendor_zoom.revoke_zoom(adapter, "u1") is False

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            return_value={
                "users": [
                    {
                        "id": "u1",
                        "email": "zoom@example.com",
                        "first_name": "Zoom",
                        "last_name": "User",
                        "last_login_time": "2026-01-20T00:00:00Z",
                        "role_name": "Owner",
                        "status": "active",
                    },
                    {"id": "u2", "last_login_time": "bad", "status": "inactive"},
                    {"id": "u3", "status": "active"},
                ]
            }
        ),
    ):
        rows = await vendor_zoom.list_zoom_activity(adapter, parse_timestamp_fn=parse_timestamp)
    assert len(rows) == 3
    assert rows[0]["is_admin"] is True
    assert rows[1]["suspended"] is True
    assert rows[2]["last_active_at"] is None

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_zoom.list_zoom_activity(adapter, parse_timestamp_fn=parse_timestamp) == []


@pytest.mark.asyncio
async def test_slack_revoke_and_activity_paths() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="slack",
            auth_method="oauth",
            connector_config={"slack_team_id": "T123"},
        )
    )

    with patch(
        "app.shared.core.http.get_http_client",
        return_value=_SequenceClient([_FakeResponse(200, {"ok": True})]),
    ):
        assert await vendor_slack.revoke_slack(adapter, "U1") is True
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=_SequenceClient([_FakeResponse(200, {"ok": False, "error": "cant"})]),
    ):
        assert await vendor_slack.revoke_slack(adapter, "U1") is False
    with patch(
        "app.shared.core.http.get_http_client",
        return_value=_SequenceClient([httpx.ConnectError("x")]),
    ):
        assert await vendor_slack.revoke_slack(adapter, "U1") is False

    no_team = LicenseAdapter(_conn(vendor="slack", auth_method="oauth", connector_config={}))
    assert await vendor_slack.revoke_slack(no_team, "U1") is False

    with patch.object(adapter, "_get_json", new=AsyncMock(return_value={"ok": False, "error": "plan"})):
        assert await vendor_slack.list_slack_activity(adapter) == []

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            side_effect=[
                {"ok": True, "logins": [{"user_id": "U1", "date_last": 1700000000}]},
                {
                    "members": [
                        {
                            "id": "U1",
                            "profile": {"email": "slack@example.com"},
                            "real_name": "Slack User",
                            "is_admin": True,
                            "deleted": False,
                        }
                    ]
                },
            ]
        ),
    ):
        rows = await vendor_slack.list_slack_activity(adapter)
    assert rows[0]["user_id"] == "U1"
    assert rows[0]["is_admin"] is True
    assert rows[0]["last_active_at"] is not None

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_slack.list_slack_activity(adapter) == []


@pytest.mark.asyncio
async def test_salesforce_revoke_and_activity_paths() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="salesforce",
            auth_method="oauth",
            connector_config={"instance_url": "https://acme.my.salesforce.com"},
        )
    )

    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([_FakeResponse(204)])):
        assert await vendor_salesforce.revoke_salesforce(adapter, "u1") is True
    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([_FakeResponse(500)])):
        assert await vendor_salesforce.revoke_salesforce(adapter, "u1") is False
    with patch("app.shared.core.http.get_http_client", return_value=_SequenceClient([httpx.ConnectError("x")])):
        assert await vendor_salesforce.revoke_salesforce(adapter, "u1") is False

    no_url = LicenseAdapter(_conn(vendor="salesforce", auth_method="oauth", connector_config={}))
    assert await vendor_salesforce.revoke_salesforce(no_url, "u1") is False
    assert await vendor_salesforce.list_salesforce_activity(no_url, parse_timestamp_fn=parse_timestamp) == []

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            return_value={
                "records": [
                    {
                        "Id": "u1",
                        "Email": "sf@example.com",
                        "Name": "Sales Force",
                        "LastLoginDate": "2026-01-15T00:00:00Z",
                        "IsActive": False,
                        "Profile": {"Name": "System Administrator"},
                    },
                    {"Id": "u2", "LastLoginDate": "bad", "Profile": {}},
                    {"Id": "u3", "Email": "nolast@example.com", "Profile": {}},
                ]
            }
        ),
    ):
        rows = await vendor_salesforce.list_salesforce_activity(adapter, parse_timestamp_fn=parse_timestamp)
    assert len(rows) == 3
    assert rows[0]["is_admin"] is True
    assert rows[0]["suspended"] is True
    assert isinstance(rows[1]["last_active_at"], datetime)
    assert rows[2]["last_active_at"] is None

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_salesforce.list_salesforce_activity(adapter, parse_timestamp_fn=parse_timestamp) == []


@pytest.mark.asyncio
async def test_google_workspace_activity_and_misc_methods() -> None:
    adapter = LicenseAdapter(_conn(vendor="google_workspace", auth_method="oauth"))

    with patch.object(
        adapter,
        "_get_json",
        new=AsyncMock(
            return_value={
                "users": [
                    {
                        "primaryEmail": "gw@example.com",
                        "lastLoginTime": "2026-01-18T00:00:00Z",
                        "name": {"fullName": "GW User"},
                        "isAdmin": True,
                        "suspended": False,
                        "creationTime": "2025-01-01T00:00:00Z",
                    },
                    {"primaryEmail": "gw2@example.com", "name": {"fullName": "GW User 2"}},
                ]
            }
        ),
    ):
        rows = await vendor_google.list_google_workspace_activity(adapter, parse_timestamp_fn=parse_timestamp)
    assert rows[0]["email"] == "gw@example.com"
    assert rows[0]["is_admin"] is True
    assert rows[0]["last_active_at"] == datetime(2026, 1, 18, tzinfo=timezone.utc)
    assert rows[1]["last_active_at"] is None

    with patch.object(adapter, "_get_json", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
        assert await vendor_google.list_google_workspace_activity(adapter, parse_timestamp_fn=parse_timestamp) == []

    with patch.object(
        adapter,
        "list_users_activity",
        new=AsyncMock(
            return_value=[
                {
                    "user_id": "gw-1",
                    "email": "gw@example.com",
                    "full_name": "GW User",
                    "last_active_at": datetime(2026, 1, 18, tzinfo=timezone.utc),
                    "is_admin": True,
                    "suspended": False,
                }
            ]
        ),
    ):
        discovered = await adapter.discover_resources("license")
        usage = await adapter.get_resource_usage("license", "gw-1")

    assert len(discovered) == 1
    assert discovered[0]["id"] == "gw-1"
    assert discovered[0]["metadata"]["is_admin"] is True
    assert len(usage) == 1
    assert usage[0]["resource_id"] == "gw-1"
    assert usage[0]["usage_amount"] == 1.0


@pytest.mark.asyncio
async def test_discover_resources_and_usage_from_manual_feed_and_filters() -> None:
    adapter = LicenseAdapter(
        _conn(
            vendor="custom",
            auth_method="manual",
            connector_config={"default_seat_price_usd": 29.5, "currency": "eur"},
            license_feed=[
                {
                    "user_id": "u-1",
                    "email": "u1@example.com",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "name": "User One",
                },
                {
                    "user_id": "u-2",
                    "email": "u2@example.com",
                    "timestamp": "2026-01-02T00:00:00Z",
                    "status": "suspended",
                },
            ],
        )
    )
    adapter.last_error = "stale"

    discovered = await adapter.discover_resources("licenses", region="eu-west-1")
    assert len(discovered) == 2
    assert discovered[0]["region"] == "eu-west-1"
    assert discovered[0]["type"] == "license_seat"
    assert discovered[1]["status"] == "suspended"

    usage_rows = await adapter.get_resource_usage("license", "u-2")
    assert len(usage_rows) == 1
    assert usage_rows[0]["resource_id"] == "u-2"
    assert usage_rows[0]["cost_usd"] == 29.5
    assert usage_rows[0]["currency"] == "EUR"
    assert usage_rows[0]["tags"]["suspended"] is True
    assert adapter.last_error is None

    assert await adapter.discover_resources("compute") == []
    assert await adapter.get_resource_usage("compute") == []


@pytest.mark.asyncio
async def test_discover_resources_and_usage_fail_closed_on_activity_errors() -> None:
    adapter = LicenseAdapter(_conn(vendor="github", auth_method="oauth"))
    with patch.object(
        adapter,
        "list_users_activity",
        new=AsyncMock(side_effect=ExternalAPIError("activity down")),
    ):
        assert await adapter.discover_resources("license") == []
        assert await adapter.get_resource_usage("license", "user-1") == []
    assert "activity down" in str(adapter.last_error)
