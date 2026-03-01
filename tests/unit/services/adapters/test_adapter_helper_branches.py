from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.shared.adapters.hybrid import HybridAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.core.exceptions import ExternalAPIError


class _SecretToken:
    def __init__(self, value: str):
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _license_conn(**overrides: object) -> MagicMock:
    conn = MagicMock()
    conn.auth_method = overrides.get("auth_method", "manual")
    conn.vendor = overrides.get("vendor", "generic")
    conn.api_key = overrides.get("api_key")
    conn.connector_config = overrides.get("connector_config", {})
    conn.license_feed = overrides.get("license_feed", [])
    return conn


def _platform_conn(**overrides: object) -> MagicMock:
    conn = MagicMock()
    conn.auth_method = overrides.get("auth_method", "manual")
    conn.vendor = overrides.get("vendor", "generic")
    conn.api_key = overrides.get("api_key")
    conn.api_secret = overrides.get("api_secret")
    conn.connector_config = overrides.get("connector_config", {})
    conn.spend_feed = overrides.get("spend_feed", [])
    return conn


def _hybrid_conn(**overrides: object) -> MagicMock:
    conn = MagicMock()
    conn.auth_method = overrides.get("auth_method", "manual")
    conn.vendor = overrides.get("vendor", "generic")
    conn.api_key = overrides.get("api_key")
    conn.api_secret = overrides.get("api_secret")
    conn.connector_config = overrides.get("connector_config", {})
    conn.spend_feed = overrides.get("spend_feed", [])
    return conn


@pytest.mark.parametrize(
    ("auth_method", "vendor", "expected"),
    [
        ("oauth", "microsoft365", "microsoft_365"),
        ("api_key", "googleworkspace", "google_workspace"),
        ("oauth", "github_enterprise", "github"),
        ("oauth", "slack_enterprise", "slack"),
        ("oauth", "zoom", "zoom"),
        ("oauth", "sfdc", "salesforce"),
        ("manual", "microsoft_365", None),
        ("oauth", "unknown_vendor", None),
    ],
)
def test_license_native_vendor_alias_mapping(
    auth_method: str, vendor: str, expected: str | None
) -> None:
    adapter = LicenseAdapter(_license_conn(auth_method=auth_method, vendor=vendor))
    assert adapter._native_vendor == expected


def test_license_token_and_normalizer_helpers() -> None:
    adapter = LicenseAdapter(
        _license_conn(
            auth_method="oauth",
            vendor="microsoft_365",
            api_key=_SecretToken("  token-value  "),
        )
    )
    assert adapter._resolve_api_key() == "token-value"

    assert LicenseAdapter._normalize_text(None) is None
    assert LicenseAdapter._normalize_text("  hello ") == "hello"
    assert LicenseAdapter._normalize_text("   ") is None

    assert LicenseAdapter._normalize_email(" User@Example.COM ") == "user@example.com"
    assert LicenseAdapter._normalize_email("not-an-email") is None
    assert LicenseAdapter._normalize_email(None) is None

    assert LicenseAdapter._coerce_bool(True) is True
    assert LicenseAdapter._coerce_bool(1) is True
    assert LicenseAdapter._coerce_bool("yes") is True
    assert LicenseAdapter._coerce_bool("off") is False
    assert LicenseAdapter._coerce_bool(object()) is False

    missing = LicenseAdapter(
        _license_conn(auth_method="oauth", vendor="microsoft_365", api_key=None)
    )
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        missing._resolve_api_key()

    blank = LicenseAdapter(
        _license_conn(auth_method="oauth", vendor="microsoft_365", api_key="   ")
    )
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        blank._resolve_api_key()


@pytest.mark.asyncio
async def test_license_verify_connection_sets_generic_manual_error_when_validator_does_not() -> None:
    adapter = LicenseAdapter(_license_conn(auth_method="manual", vendor="generic"))
    with patch.object(adapter, "_validate_manual_feed", return_value=False):
        assert await adapter.verify_connection() is False
    assert adapter.last_error == "License feed is missing or invalid."


@pytest.mark.parametrize(
    ("auth_method", "vendor", "expected"),
    [
        ("api_key", "ledger", "ledger_http"),
        ("api_key", "datadog", "datadog"),
        ("api_key", "new-relic", "newrelic"),
        ("manual", "ledger_http", None),
        ("api_key", "custom_vendor", None),
    ],
)
def test_platform_native_vendor_alias_mapping(
    auth_method: str, vendor: str, expected: str | None
) -> None:
    adapter = PlatformAdapter(_platform_conn(auth_method=auth_method, vendor=vendor))
    assert adapter._native_vendor == expected


def test_platform_native_handler_resolution_maps_supported_vendors() -> None:
    adapter = PlatformAdapter(_platform_conn(auth_method="api_key", vendor="ledger"))
    assert adapter._resolve_native_verify_handler("ledger_http") is not None
    assert adapter._resolve_native_stream_handler("ledger_http") is not None
    assert adapter._resolve_native_verify_handler("datadog") is not None
    assert adapter._resolve_native_stream_handler("datadog") is not None
    assert adapter._resolve_native_verify_handler("newrelic") is not None
    assert adapter._resolve_native_stream_handler("newrelic") is not None
    assert adapter._resolve_native_verify_handler("unknown") is None
    assert adapter._resolve_native_stream_handler("unknown") is None
    assert adapter._resolve_native_verify_handler(None) is None
    assert adapter._resolve_native_stream_handler(None) is None


def test_platform_helper_resolvers_cover_key_branches() -> None:
    adapter = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            api_key=_SecretToken("  api-key  "),
            api_secret=_SecretToken("  app-key  "),
            connector_config={
                "api_base_url": "https://api.datadoghq.eu/",
                "unit_prices_usd": {"hosts": 2, "": 1, "invalid": -1},
                "verify_ssl": False,
            },
        )
    )
    assert adapter._resolve_api_key() == "api-key"
    assert adapter._resolve_api_secret() == "app-key"
    assert adapter._resolve_datadog_base_url() == "https://api.datadoghq.eu"
    assert adapter._resolve_verify_ssl() is False
    assert adapter._resolve_unit_prices() == {"hosts": 2.0}

    months = adapter._iter_month_starts(
        datetime(2026, 12, 15, tzinfo=timezone.utc),
        datetime(2027, 2, 2, tzinfo=timezone.utc),
    )
    assert months == [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)]

    site_adapter = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"site": "datadoghq.com"},
        )
    )
    assert site_adapter._resolve_datadog_base_url() == "https://api.datadoghq.com"

    url_site_adapter = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"site": "https://api.datadoghq.com/"},
        )
    )
    assert url_site_adapter._resolve_datadog_base_url() == "https://api.datadoghq.com"

    default_site_adapter = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="datadog", connector_config={})
    )
    assert default_site_adapter._resolve_datadog_base_url() == "https://api.datadoghq.com"


def test_platform_helper_resolvers_raise_for_invalid_config() -> None:
    bad_key = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="datadog", api_key=None)
    )
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        bad_key._resolve_api_key()

    blank_secret = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="datadog", api_secret="   ")
    )
    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        blank_secret._resolve_api_secret()

    bad_datadog_url = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"api_base_url": "datadog.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        bad_datadog_url._resolve_datadog_base_url()

    bad_datadog_site = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"site": "datadoghq.com/path"},
        )
    )
    with pytest.raises(ExternalAPIError, match="hostname, not a path"):
        bad_datadog_site._resolve_datadog_base_url()

    bad_newrelic_endpoint = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="newrelic",
            connector_config={"api_base_url": "newrelic.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        bad_newrelic_endpoint._resolve_newrelic_endpoint()

    default_newrelic_endpoint = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="newrelic", connector_config={})
    )
    assert (
        default_newrelic_endpoint._resolve_newrelic_endpoint()
        == "https://api.newrelic.com/graphql"
    )

    missing_prices = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"unit_prices_usd": {}},
        )
    )
    with pytest.raises(ExternalAPIError, match="unit_prices_usd"):
        missing_prices._resolve_unit_prices()

    invalid_prices = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"unit_prices_usd": {"hosts": -1, "apm": 0}},
        )
    )
    with pytest.raises(ExternalAPIError, match="positive numeric"):
        invalid_prices._resolve_unit_prices()

    ssl_fallback = PlatformAdapter(
        _platform_conn(
            auth_method="api_key",
            vendor="datadog",
            connector_config={"ssl_verify": False},
        )
    )
    assert ssl_fallback._resolve_verify_ssl() is False


@pytest.mark.asyncio
async def test_platform_verify_connection_validation_and_error_paths() -> None:
    unsupported_vendor = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="custom")
    )
    assert await unsupported_vendor.verify_connection() is False
    assert "not supported" in (unsupported_vendor.last_error or "").lower()

    invalid_auth = PlatformAdapter(_platform_conn(auth_method="token", vendor="ledger"))
    assert await invalid_auth.verify_connection() is False
    assert "must be one of" in (invalid_auth.last_error or "").lower()

    adapter = PlatformAdapter(_platform_conn(auth_method="manual", vendor="generic"))
    with patch.object(adapter, "_validate_manual_feed", return_value=False):
        assert await adapter.verify_connection() is False
    assert adapter.last_error == "Spend feed is missing or invalid."

    datadog_verify_error = PlatformAdapter(
        _platform_conn(auth_method="api_key", vendor="datadog")
    )
    with patch.object(
        datadog_verify_error,
        "_verify_datadog",
        new=AsyncMock(side_effect=ExternalAPIError("datadog down")),
    ):
        assert await datadog_verify_error.verify_connection() is False
    assert "datadog down" in (datadog_verify_error.last_error or "")


@pytest.mark.parametrize(
    ("auth_method", "vendor", "expected"),
    [
        ("api_key", "ledger", "ledger_http"),
        ("api_key", "openstack", "cloudkitty"),
        ("api_key", "vcenter", "vmware"),
        ("manual", "openstack", None),
        ("api_key", "custom_vendor", None),
    ],
)
def test_hybrid_native_vendor_alias_mapping(
    auth_method: str, vendor: str, expected: str | None
) -> None:
    adapter = HybridAdapter(_hybrid_conn(auth_method=auth_method, vendor=vendor))
    assert adapter._native_vendor == expected


def test_hybrid_native_handler_resolution_maps_supported_vendors() -> None:
    adapter = HybridAdapter(_hybrid_conn(auth_method="api_key", vendor="ledger"))
    assert adapter._resolve_native_verify_handler("ledger_http") is not None
    assert adapter._resolve_native_stream_handler("ledger_http") is not None
    assert adapter._resolve_native_verify_handler("cloudkitty") is not None
    assert adapter._resolve_native_stream_handler("cloudkitty") is not None
    assert adapter._resolve_native_verify_handler("vmware") is not None
    assert adapter._resolve_native_stream_handler("vmware") is not None
    assert adapter._resolve_native_verify_handler("unknown") is None
    assert adapter._resolve_native_stream_handler("unknown") is None
    assert adapter._resolve_native_verify_handler(None) is None
    assert adapter._resolve_native_stream_handler(None) is None


def test_hybrid_helper_resolvers_cover_url_ssl_and_pricing_branches() -> None:
    adapter = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            api_key=_SecretToken("  app-cred-id "),
            api_secret=_SecretToken("  app-cred-secret "),
            connector_config={
                "auth_url": "https://keystone.example.com/v3",
                "cloudkitty_base_url": "https://cloudkitty.example.com/",
                "base_url": "https://vcenter.example.com/",
                "cpu_hour_usd": 0.1,
                "ram_gb_hour_usd": 0.02,
                "ssl_verify": False,
            },
        )
    )
    assert adapter._resolve_api_key() == "app-cred-id"
    assert adapter._resolve_api_secret() == "app-cred-secret"
    assert (
        adapter._resolve_openstack_auth_url()
        == "https://keystone.example.com/v3/auth/tokens"
    )
    assert adapter._resolve_cloudkitty_base_url() == "https://cloudkitty.example.com"
    assert adapter._resolve_vmware_base_url() == "https://vcenter.example.com"
    assert adapter._resolve_vmware_pricing() == (0.1, 0.02)
    assert adapter._resolve_verify_ssl() is False

    months = adapter._iter_month_starts(
        datetime(2026, 12, 15, tzinfo=timezone.utc),
        datetime(2027, 2, 2, tzinfo=timezone.utc),
    )
    assert months == [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)]

    exact_openstack_url = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            connector_config={"auth_url": "https://keystone.example.com/v3/auth/tokens"},
        )
    )
    assert (
        exact_openstack_url._resolve_openstack_auth_url()
        == "https://keystone.example.com/v3/auth/tokens"
    )

    root_openstack_url = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            connector_config={"auth_url": "https://keystone.example.com"},
        )
    )
    assert (
        root_openstack_url._resolve_openstack_auth_url()
        == "https://keystone.example.com/v3/auth/tokens"
    )


def test_hybrid_helper_resolvers_raise_for_invalid_config() -> None:
    bad_key = HybridAdapter(_hybrid_conn(auth_method="api_key", vendor="openstack"))
    with pytest.raises(ExternalAPIError, match="Missing API token"):
        bad_key._resolve_api_key()

    bad_secret = HybridAdapter(
        _hybrid_conn(auth_method="api_key", vendor="openstack", api_secret="   ")
    )
    with pytest.raises(ExternalAPIError, match="Missing API secret"):
        bad_secret._resolve_api_secret()

    missing_auth_url = HybridAdapter(
        _hybrid_conn(auth_method="api_key", vendor="openstack", connector_config={})
    )
    with pytest.raises(ExternalAPIError, match="auth_url is required"):
        missing_auth_url._resolve_openstack_auth_url()

    invalid_auth_url = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            connector_config={"auth_url": "keystone.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        invalid_auth_url._resolve_openstack_auth_url()

    missing_cloudkitty = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            connector_config={"auth_url": "https://keystone.example.com"},
        )
    )
    with pytest.raises(ExternalAPIError, match="cloudkitty_base_url is required"):
        missing_cloudkitty._resolve_cloudkitty_base_url()

    invalid_cloudkitty = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="openstack",
            connector_config={"cloudkitty_base_url": "cloudkitty.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        invalid_cloudkitty._resolve_cloudkitty_base_url()

    missing_vmware_base = HybridAdapter(
        _hybrid_conn(auth_method="api_key", vendor="vmware", connector_config={})
    )
    with pytest.raises(ExternalAPIError, match="base_url is required"):
        missing_vmware_base._resolve_vmware_base_url()

    invalid_vmware_base = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="vmware",
            connector_config={"base_url": "vcenter.local"},
        )
    )
    with pytest.raises(ExternalAPIError, match="http\\(s\\) URL"):
        invalid_vmware_base._resolve_vmware_base_url()

    invalid_vmware_pricing = HybridAdapter(
        _hybrid_conn(
            auth_method="api_key",
            vendor="vmware",
            connector_config={"cpu_hour_usd": 0, "ram_gb_hour_usd": -1},
        )
    )
    with pytest.raises(ExternalAPIError, match="cpu_hour_usd must be a positive number"):
        invalid_vmware_pricing._resolve_vmware_pricing()

    default_ssl = HybridAdapter(
        _hybrid_conn(auth_method="api_key", vendor="vmware", connector_config={})
    )
    assert default_ssl._resolve_verify_ssl() is True


@pytest.mark.asyncio
async def test_hybrid_verify_connection_validation_and_error_paths() -> None:
    unsupported_vendor = HybridAdapter(_hybrid_conn(auth_method="api_key", vendor="custom"))
    assert await unsupported_vendor.verify_connection() is False
    assert "not supported" in (unsupported_vendor.last_error or "").lower()

    invalid_auth = HybridAdapter(_hybrid_conn(auth_method="token", vendor="ledger"))
    assert await invalid_auth.verify_connection() is False
    assert "must be one of" in (invalid_auth.last_error or "").lower()

    adapter = HybridAdapter(_hybrid_conn(auth_method="manual", vendor="generic"))
    with patch.object(adapter, "_validate_manual_feed", return_value=False):
        assert await adapter.verify_connection() is False
    assert adapter.last_error == "Spend feed is missing or invalid."

    cloudkitty_verify_error = HybridAdapter(
        _hybrid_conn(auth_method="api_key", vendor="openstack")
    )
    with patch.object(
        cloudkitty_verify_error,
        "_verify_cloudkitty",
        new=AsyncMock(side_effect=ExternalAPIError("cloudkitty down")),
    ):
        assert await cloudkitty_verify_error.verify_connection() is False
    assert "cloudkitty down" in (cloudkitty_verify_error.last_error or "")
