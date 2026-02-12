import pytest
from pydantic import ValidationError

from app.schemas.connections import LicenseConnectionCreate, SaaSConnectionCreate


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
        vendor="salesforce",
        auth_method="oauth",
        api_key="token",
        connector_config={"instance_url": "https://acme.my.salesforce.com"},
        spend_feed=[],
    )

    assert payload.connector_config["instance_url"] == "https://acme.my.salesforce.com"


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
        vendor="microsoft_365",
        auth_method="oauth",
        api_key="token",
        connector_config={"sku_prices": {"SPE_E5": 57}},
        license_feed=[],
    )

    assert payload.connector_config["sku_prices"]["SPE_E5"] == 57
