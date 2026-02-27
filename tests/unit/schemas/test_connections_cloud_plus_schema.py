import pytest
from pydantic import ValidationError

from app.schemas.connections import (
    HybridConnectionCreate,
    LicenseConnectionCreate,
    PlatformConnectionCreate,
    SaaSConnectionCreate,
)


def test_saas_salesforce_native_requires_instance_url() -> None:
    with pytest.raises(ValidationError):
        SaaSConnectionCreate(
            name="Salesforce Native",
            vendor="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={},
            spend_feed=[],
        )


def test_saas_salesforce_native_accepts_instance_url() -> None:
    payload = SaaSConnectionCreate(
        name="Salesforce Native",
        vendor="Salesforce",
        auth_method="oauth",
        api_key="token",
        connector_config={"instance_url": "https://acme.my.salesforce.com"},
        spend_feed=[],
    )

    assert payload.vendor == "salesforce"
    assert payload.connector_config["instance_url"] == "https://acme.my.salesforce.com"


def test_saas_native_rejects_unsupported_vendor() -> None:
    with pytest.raises(ValidationError):
        SaaSConnectionCreate(
            name="HubSpot Native",
            vendor="hubspot",
            auth_method="oauth",
            api_key="token",
            connector_config={},
            spend_feed=[],
        )


def test_license_connector_rejects_invalid_sku_prices_shape() -> None:
    with pytest.raises(ValidationError):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="token",
            connector_config={"sku_prices": ["bad"]},
            license_feed=[],
        )


def test_license_connector_accepts_numeric_sku_prices() -> None:
    payload = LicenseConnectionCreate(
        name="M365",
        vendor="Microsoft_365",
        auth_method="oauth",
        api_key="token",
        connector_config={"sku_prices": {"SPE_E5": 57}},
        license_feed=[],
    )

    assert payload.vendor == "microsoft_365"
    assert payload.connector_config["sku_prices"]["SPE_E5"] == 57


def test_license_native_rejects_unsupported_vendor() -> None:
    with pytest.raises(ValidationError):
        LicenseConnectionCreate(
            name="Flexera Native",
            vendor="flexera",
            auth_method="oauth",
            api_key="token",
            connector_config={},
            license_feed=[],
        )


def test_license_native_accepts_google_workspace_vendor() -> None:
    payload = LicenseConnectionCreate(
        name="Google Workspace",
        vendor="google_workspace",
        auth_method="oauth",
        api_key="token",
        connector_config={},
        license_feed=[],
    )

    assert payload.vendor == "google_workspace"


def test_license_salesforce_native_requires_instance_url() -> None:
    with pytest.raises(ValidationError):
        LicenseConnectionCreate(
            name="Salesforce License Native",
            vendor="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={},
            license_feed=[],
        )


def test_license_salesforce_native_accepts_instance_url() -> None:
    payload = LicenseConnectionCreate(
        name="Salesforce License Native",
        vendor="salesforce",
        auth_method="oauth",
        api_key="token",
        connector_config={"salesforce_instance_url": "https://acme.my.salesforce.com"},
        license_feed=[],
    )

    assert payload.vendor == "salesforce"


def test_license_rejects_negative_default_seat_price() -> None:
    with pytest.raises(ValidationError):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="token",
            connector_config={"default_seat_price_usd": -1},
            license_feed=[],
        )


def test_saas_rejects_blank_name_and_vendor() -> None:
    with pytest.raises(ValidationError, match="name must not be empty"):
        SaaSConnectionCreate(
            name="   ",
            vendor="salesforce",
            auth_method="manual",
            connector_config={},
            spend_feed=[],
        )
    with pytest.raises(ValidationError, match="vendor must not be empty"):
        SaaSConnectionCreate(
            name="Valid Name",
            vendor="   ",
            auth_method="manual",
            connector_config={},
            spend_feed=[],
        )


def test_saas_rejects_invalid_auth_method() -> None:
    with pytest.raises(
        ValidationError, match="auth_method must be one of: manual, api_key, oauth, csv"
    ):
        SaaSConnectionCreate(
            name="Stripe",
            vendor="stripe",
            auth_method="token",
            connector_config={},
            spend_feed=[],
        )


def test_saas_native_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="api_key is required"):
        SaaSConnectionCreate(
            name="Stripe Native",
            vendor="stripe",
            auth_method="oauth",
            api_key=None,
            connector_config={},
            spend_feed=[],
        )


def test_saas_salesforce_rejects_non_http_instance_url() -> None:
    with pytest.raises(ValidationError, match="instance_url must be an http\\(s\\) URL"):
        SaaSConnectionCreate(
            name="Salesforce Native",
            vendor="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={"instance_url": "ftp://acme.my.salesforce.com"},
            spend_feed=[],
        )


def test_license_rejects_invalid_auth_method() -> None:
    with pytest.raises(
        ValidationError, match="auth_method must be one of: manual, api_key, oauth, csv"
    ):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="token",
            connector_config={},
            license_feed=[],
        )


def test_license_native_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="api_key is required"):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key=None,
            connector_config={},
            license_feed=[],
        )


def test_license_salesforce_rejects_non_http_instance_url() -> None:
    with pytest.raises(
        ValidationError, match="salesforce_instance_url must be an http\\(s\\) URL"
    ):
        LicenseConnectionCreate(
            name="Salesforce License Native",
            vendor="salesforce",
            auth_method="oauth",
            api_key="token",
            connector_config={"salesforce_instance_url": "ftp://acme.my.salesforce.com"},
            license_feed=[],
        )


def test_license_rejects_non_numeric_default_seat_price() -> None:
    with pytest.raises(
        ValidationError, match="default_seat_price_usd must be numeric"
    ):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="token",
            connector_config={"default_seat_price_usd": "12.0"},
            license_feed=[],
        )


def test_license_rejects_non_string_sku_keys() -> None:
    with pytest.raises(ValidationError, match="sku_prices keys must be strings"):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="token",
            connector_config={"sku_prices": {123: 12.0}},
            license_feed=[],
        )


def test_license_rejects_non_numeric_sku_values() -> None:
    with pytest.raises(ValidationError, match="sku_prices values must be numeric"):
        LicenseConnectionCreate(
            name="M365",
            vendor="microsoft_365",
            auth_method="oauth",
            api_key="token",
            connector_config={"sku_prices": {"E5": "12.0"}},
            license_feed=[],
        )


def _platform_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Platform Connector",
        "vendor": "ledger_http",
        "auth_method": "manual",
        "api_key": None,
        "api_secret": None,
        "connector_config": {},
        "spend_feed": [],
    }
    payload.update(overrides)
    return payload


def _hybrid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Hybrid Connector",
        "vendor": "ledger_http",
        "auth_method": "manual",
        "api_key": None,
        "api_secret": None,
        "connector_config": {},
        "spend_feed": [],
    }
    payload.update(overrides)
    return payload


def test_platform_rejects_invalid_auth_method() -> None:
    with pytest.raises(
        ValidationError, match="auth_method must be one of: manual, csv, api_key"
    ):
        PlatformConnectionCreate(**_platform_payload(auth_method="oauth"))


def test_platform_native_requires_api_key_and_supported_vendor() -> None:
    with pytest.raises(ValidationError, match="api_key is required"):
        PlatformConnectionCreate(
            **_platform_payload(auth_method="api_key", api_key=None, vendor="ledger_http")
        )
    with pytest.raises(ValidationError, match="native Platform auth currently supports"):
        PlatformConnectionCreate(
            **_platform_payload(auth_method="api_key", api_key="token", vendor="custom")
        )


def test_platform_ledger_native_requires_http_base_url() -> None:
    with pytest.raises(ValidationError, match="base_url is required"):
        PlatformConnectionCreate(
            **_platform_payload(auth_method="api_key", api_key="token", vendor="ledger_http")
        )
    with pytest.raises(ValidationError, match="base_url must be an http\\(s\\) URL"):
        PlatformConnectionCreate(
            **_platform_payload(
                auth_method="api_key",
                api_key="token",
                vendor="ledger_http",
                connector_config={"base_url": "ftp://ledger.example.com"},
            )
        )


def test_platform_datadog_native_requires_secret_and_unit_prices() -> None:
    with pytest.raises(ValidationError, match="api_secret is required for Datadog"):
        PlatformConnectionCreate(
            **_platform_payload(auth_method="api_key", api_key="token", vendor="datadog")
        )
    with pytest.raises(
        ValidationError, match="unit_prices_usd must be a non-empty object for Datadog pricing"
    ):
        PlatformConnectionCreate(
            **_platform_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="app-secret",
                vendor="datadog",
                connector_config={"unit_prices_usd": {}},
            )
        )


def test_platform_newrelic_native_requires_account_nrql_and_unit_prices() -> None:
    with pytest.raises(ValidationError, match="account_id is required for New Relic"):
        PlatformConnectionCreate(
            **_platform_payload(
                auth_method="api_key",
                api_key="token",
                vendor="newrelic",
                connector_config={"nrql_template": "SELECT 1", "unit_prices_usd": {"gb": 1}},
            )
        )
    with pytest.raises(ValidationError, match="nrql_template is required for New Relic"):
        PlatformConnectionCreate(
            **_platform_payload(
                auth_method="api_key",
                api_key="token",
                vendor="newrelic",
                connector_config={"account_id": 1234, "unit_prices_usd": {"gb": 1}},
            )
        )
    with pytest.raises(
        ValidationError,
        match="unit_prices_usd must be a non-empty object for New Relic pricing",
    ):
        PlatformConnectionCreate(
            **_platform_payload(
                auth_method="api_key",
                api_key="token",
                vendor="newrelic",
                connector_config={"account_id": "1234", "nrql_template": "SELECT 1"},
            )
        )


def test_hybrid_rejects_invalid_auth_method() -> None:
    with pytest.raises(
        ValidationError, match="auth_method must be one of: manual, csv, api_key"
    ):
        HybridConnectionCreate(**_hybrid_payload(auth_method="oauth"))


def test_hybrid_native_requires_api_key_and_supported_vendor() -> None:
    with pytest.raises(ValidationError, match="api_key is required"):
        HybridConnectionCreate(
            **_hybrid_payload(auth_method="api_key", api_key=None, vendor="ledger_http")
        )
    with pytest.raises(ValidationError, match="native Hybrid auth currently supports"):
        HybridConnectionCreate(
            **_hybrid_payload(auth_method="api_key", api_key="token", vendor="custom")
        )


def test_hybrid_ledger_native_requires_http_base_url() -> None:
    with pytest.raises(ValidationError, match="base_url is required"):
        HybridConnectionCreate(
            **_hybrid_payload(auth_method="api_key", api_key="token", vendor="ledger_http")
        )
    with pytest.raises(ValidationError, match="base_url must be an http\\(s\\) URL"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                vendor="ledger_http",
                connector_config={"base_url": "ssh://ledger.example.com"},
            )
        )


def test_hybrid_openstack_native_requires_all_endpoints_and_secret() -> None:
    with pytest.raises(ValidationError, match="api_secret is required for OpenStack"):
        HybridConnectionCreate(
            **_hybrid_payload(auth_method="api_key", api_key="token", vendor="openstack")
        )
    with pytest.raises(ValidationError, match="auth_url is required"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="openstack",
                connector_config={"cloudkitty_base_url": "https://cloudkitty.local"},
            )
        )
    with pytest.raises(ValidationError, match="auth_url must be an http\\(s\\) URL"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="openstack",
                connector_config={
                    "auth_url": "ftp://keystone.local",
                    "cloudkitty_base_url": "https://cloudkitty.local",
                },
            )
        )
    with pytest.raises(ValidationError, match="cloudkitty_base_url is required"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="openstack",
                connector_config={"auth_url": "https://keystone.local"},
            )
        )
    with pytest.raises(
        ValidationError, match="cloudkitty_base_url must be an http\\(s\\) URL"
    ):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="openstack",
                connector_config={
                    "auth_url": "https://keystone.local",
                    "cloudkitty_base_url": "file://cloudkitty.local",
                },
            )
        )


def test_hybrid_vmware_native_requires_pricing_and_valid_urls() -> None:
    with pytest.raises(ValidationError, match="api_secret is required for VMware"):
        HybridConnectionCreate(
            **_hybrid_payload(auth_method="api_key", api_key="token", vendor="vmware")
        )
    with pytest.raises(ValidationError, match="base_url is required for VMware"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="vmware",
            )
        )
    with pytest.raises(ValidationError, match="base_url must be an http\\(s\\) URL"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="vmware",
                connector_config={"base_url": "vmware.local"},
            )
        )
    with pytest.raises(ValidationError, match="cpu_hour_usd must be a positive number"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="vmware",
                connector_config={
                    "base_url": "https://vcenter.local",
                    "cpu_hour_usd": 0,
                    "ram_gb_hour_usd": 0.01,
                },
            )
        )
    with pytest.raises(ValidationError, match="ram_gb_hour_usd must be a positive number"):
        HybridConnectionCreate(
            **_hybrid_payload(
                auth_method="api_key",
                api_key="token",
                api_secret="secret",
                vendor="vmware",
                connector_config={
                    "base_url": "https://vcenter.local",
                    "cpu_hour_usd": 0.02,
                    "ram_gb_hour_usd": 0,
                },
            )
        )
