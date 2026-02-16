from uuid import UUID
from datetime import datetime
from typing import Any, Self
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

_SAAS_NATIVE_VENDORS = {"stripe", "salesforce"}
_LICENSE_NATIVE_VENDORS = {"microsoft_365", "microsoft365", "m365", "microsoft"}
_LEDGER_NATIVE_VENDORS = {"ledger_http", "cmdb_ledger", "cmdb-ledger", "ledger"}
_PLATFORM_NATIVE_VENDORS = {
    *_LEDGER_NATIVE_VENDORS,
    "datadog",
    "newrelic",
    "new_relic",
    "new-relic",
}
_HYBRID_NATIVE_VENDORS = {
    *_LEDGER_NATIVE_VENDORS,
    "openstack",
    "cloudkitty",
    "vmware",
    "vcenter",
    "vsphere",
}


def _normalize_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


class AWSConnectionCreate(BaseModel):
    """Request body for creating a new AWS connection."""

    aws_account_id: str = Field(
        ..., pattern=r"^\d{12}$", description="12-digit AWS account ID"
    )
    role_arn: str = Field(
        ...,
        pattern=r"^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$",
        description="Full ARN of the IAM role to assume",
    )
    external_id: str = Field(
        ..., pattern=r"^vx-[a-f0-9]{32}$", description="External ID from setup step"
    )
    region: str = Field(
        default="us-east-1", max_length=20, description="AWS region for Cost Explorer"
    )
    is_management_account: bool = Field(
        default=False,
        description="Whether this is a Management Account for Organizations",
    )
    organization_id: str | None = Field(
        default=None, max_length=12, description="AWS Organization ID"
    )


class AWSConnectionResponse(BaseModel):
    """Response body for AWS connection."""

    id: UUID
    aws_account_id: str
    role_arn: str
    region: str
    status: str
    last_verified_at: datetime | None
    error_message: str | None
    is_management_account: bool
    organization_id: str | None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AWSConnectionSetup(BaseModel):
    """Response for initial setup - includes external_id for CloudFormation."""

    external_id: str
    instructions: str


class DiscoveredAccountResponse(BaseModel):
    id: UUID
    account_id: str
    name: str | None
    email: str | None
    status: str
    last_discovered_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class TemplateResponse(BaseModel):
    """Response containing template content for IAM role setup."""

    external_id: str
    cloudformation_yaml: str
    terraform_hcl: str
    magic_link: str
    instructions: str
    permissions_summary: list[str]


class AzureConnectionCreate(BaseModel):
    """Azure Service Principal connection request."""

    name: str = Field(
        ..., min_length=3, max_length=100, description="Friendly name for connection"
    )
    azure_tenant_id: str = Field(
        ..., max_length=50, description="Azure Tenant ID (Directory ID)"
    )
    client_id: str = Field(..., max_length=50, description="Application ID")
    subscription_id: str = Field(..., max_length=50, description="Subscription ID")
    client_secret: str | None = Field(
        default=None,
        max_length=255,
        description="Client Secret (Optional for Workload Identity)",
    )
    auth_method: str = Field(
        default="secret", max_length=20, description="secret or workload_identity"
    )

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"secret", "workload_identity"}:
            raise ValueError("auth_method must be 'secret' or 'workload_identity'")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self) -> Self:
        if self.auth_method == "secret" and not self.client_secret:
            raise ValueError("client_secret is required when auth_method is 'secret'")
        return self


    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"secret", "workload_identity"}:
            raise ValueError("auth_method must be 'secret' or 'workload_identity'")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self):
        if self.auth_method == "secret" and not self.client_secret:
            raise ValueError("client_secret is required when auth_method is 'secret'")
        return self

class AzureConnectionResponse(BaseModel):
    id: UUID
    name: str
    azure_tenant_id: str
    client_id: str
    subscription_id: str
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class GCPConnectionCreate(BaseModel):
    """GCP Service Account connection request."""

    name: str = Field(..., min_length=3, max_length=100, description="Friendly name")
    project_id: str = Field(..., max_length=100, description="GCP Project ID")
    service_account_json: str | None = Field(
        default=None,
        max_length=20000,
        description="Full JSON content (Optional for Workload Identity)",
    )
    auth_method: str = Field(
        default="secret", max_length=20, description="secret or workload_identity"
    )
    billing_project_id: str | None = Field(
        default=None, max_length=100, description="Project ID holding BigQuery export"
    )
    billing_dataset: str | None = Field(
        default=None, max_length=100, description="BigQuery dataset ID"
    )
    billing_table: str | None = Field(
        default=None, max_length=100, description="BigQuery table ID"
    )

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"secret", "workload_identity"}:
            raise ValueError("auth_method must be 'secret' or 'workload_identity'")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self) -> Self:
        import json

        if self.auth_method == "secret" and not self.service_account_json:
            raise ValueError(
                "service_account_json is required when auth_method is 'secret'"
            )
        if self.service_account_json:
            try:
                json.loads(self.service_account_json)
            except Exception as exc:
                raise ValueError("service_account_json must be valid JSON") from exc
        return self


    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"secret", "workload_identity"}:
            raise ValueError("auth_method must be 'secret' or 'workload_identity'")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self):
        import json
        if self.auth_method == "secret" and not self.service_account_json:
            raise ValueError("service_account_json is required when auth_method is 'secret'")
        if self.service_account_json:
            try:
                json.loads(self.service_account_json)
            except Exception as exc:
                raise ValueError("service_account_json must be valid JSON") from exc
        return self

class GCPConnectionResponse(BaseModel):
    id: UUID
    name: str
    project_id: str
    auth_method: str
    billing_project_id: str | None
    billing_dataset: str | None
    billing_table: str | None
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SaaSConnectionCreate(BaseModel):
    """SaaS Cloud+ connection request."""

    name: str = Field(..., min_length=3, max_length=100, description="Friendly name")
    vendor: str = Field(
        ..., min_length=2, max_length=100, description="SaaS vendor name"
    )
    auth_method: str = Field(
        default="manual", max_length=20, description="manual, api_key, oauth, csv"
    )
    api_key: str | None = Field(
        default=None, max_length=1024, description="Optional API key for vendor access"
    )
    connector_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Vendor-specific non-secret settings (for example Salesforce instance URL, SKU price map).",
    )
    spend_feed: list[dict[str, Any]] = Field(
        default_factory=list, description="Normalized SaaS spend records"
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _normalize_non_empty(value, "name")

    @field_validator("vendor")
    @classmethod
    def _validate_vendor(cls, value: str) -> str:
        return _normalize_non_empty(value, "vendor").lower()

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"manual", "api_key", "oauth", "csv"}:
            raise ValueError("auth_method must be one of: manual, api_key, oauth, csv")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self) -> Self:
        if self.auth_method in {"api_key", "oauth"} and not self.api_key:
            raise ValueError(
                "api_key is required when auth_method is 'api_key' or 'oauth'"
            )

        vendor = self.vendor
        native_mode = self.auth_method in {"api_key", "oauth"}
        if native_mode and vendor not in _SAAS_NATIVE_VENDORS:
            raise ValueError(
                "native SaaS auth currently supports vendors: stripe, salesforce. "
                "Use auth_method manual/csv for other vendors."
            )

        if vendor == "salesforce" and native_mode:
            instance_url = self.connector_config.get("instance_url")
            if not isinstance(instance_url, str) or not instance_url.strip():
                raise ValueError(
                    "connector_config.instance_url is required for Salesforce native connectors"
                )
            if not instance_url.strip().startswith(("https://", "http://")):
                raise ValueError("connector_config.instance_url must be an http(s) URL")
        return self


class SaaSConnectionResponse(BaseModel):
    id: UUID
    name: str
    vendor: str
    auth_method: str
    connector_config: dict[str, Any]
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class LicenseConnectionCreate(BaseModel):
    """License/ITAM Cloud+ connection request."""

    name: str = Field(..., min_length=3, max_length=100, description="Friendly name")
    vendor: str = Field(
        ..., min_length=2, max_length=100, description="License vendor name"
    )
    auth_method: str = Field(
        default="manual", max_length=20, description="manual, api_key, oauth, csv"
    )
    api_key: str | None = Field(
        default=None, max_length=1024, description="Optional API key for vendor access"
    )
    connector_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Vendor-specific non-secret settings (for example Microsoft 365 SKU pricing overrides).",
    )
    license_feed: list[dict[str, Any]] = Field(
        default_factory=list, description="Normalized license spend records"
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _normalize_non_empty(value, "name")

    @field_validator("vendor")
    @classmethod
    def _validate_vendor(cls, value: str) -> str:
        return _normalize_non_empty(value, "vendor").lower()

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"manual", "api_key", "oauth", "csv"}:
            raise ValueError("auth_method must be one of: manual, api_key, oauth, csv")
        return normalized

    @model_validator(mode="after")
    def _validate_credentials(self) -> Self:
        if self.auth_method in {"api_key", "oauth"} and not self.api_key:
            raise ValueError(
                "api_key is required when auth_method is 'api_key' or 'oauth'"
            )

        native_mode = self.auth_method in {"api_key", "oauth"}
        if native_mode and self.vendor not in _LICENSE_NATIVE_VENDORS:
            raise ValueError(
                "native license auth currently supports Microsoft 365 vendors only. "
                "Use auth_method manual/csv for other vendors."
            )

        default_seat_price = self.connector_config.get("default_seat_price_usd")
        if default_seat_price is not None and not isinstance(
            default_seat_price, (int, float)
        ):
            raise ValueError("connector_config.default_seat_price_usd must be numeric")
        if isinstance(default_seat_price, (int, float)) and default_seat_price < 0:
            raise ValueError(
                "connector_config.default_seat_price_usd cannot be negative"
            )

        sku_prices = self.connector_config.get("sku_prices")
        if sku_prices is not None:
            if not isinstance(sku_prices, dict):
                raise ValueError(
                    "connector_config.sku_prices must be a key/value object"
                )
            for key, value in sku_prices.items():
                if not isinstance(key, str):
                    raise ValueError("connector_config.sku_prices keys must be strings")
                if not isinstance(value, (int, float)):
                    raise ValueError(
                        "connector_config.sku_prices values must be numeric"
                    )
        return self


class LicenseConnectionResponse(BaseModel):
    id: UUID
    name: str
    vendor: str
    auth_method: str
    connector_config: dict[str, Any]
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PlatformConnectionCreate(BaseModel):
    """Internal Platform Cloud+ connection request (feed-based + ledger HTTP pull)."""

    name: str = Field(..., min_length=3, max_length=100, description="Friendly name")
    vendor: str = Field(
        ..., min_length=2, max_length=100, description="Platform category/vendor label"
    )
    auth_method: str = Field(
        default="manual", max_length=20, description="manual, csv, or api_key"
    )
    api_key: str | None = Field(
        default=None, max_length=1024, description="API key for native connectors"
    )
    api_secret: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional second secret for native connectors (for example Datadog application key).",
    )
    connector_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-secret settings (for example ledger HTTP base URL and path).",
    )
    spend_feed: list[dict[str, Any]] = Field(
        default_factory=list, description="Normalized platform spend records"
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _normalize_non_empty(value, "name")

    @field_validator("vendor")
    @classmethod
    def _validate_vendor(cls, value: str) -> str:
        return _normalize_non_empty(value, "vendor").lower()

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"manual", "csv", "api_key"}:
            raise ValueError("auth_method must be one of: manual, csv, api_key")
        return normalized

    @model_validator(mode="after")
    def _validate_native_config(self) -> Self:
        if self.auth_method == "api_key" and not self.api_key:
            raise ValueError("api_key is required when auth_method is 'api_key'")

        native_mode = self.auth_method == "api_key"
        if native_mode and self.vendor not in _PLATFORM_NATIVE_VENDORS:
            raise ValueError(
                "native Platform auth currently supports: ledger_http (and aliases), datadog, newrelic. "
                "Use auth_method manual/csv for custom vendors."
            )

        if native_mode:
            if self.vendor in _LEDGER_NATIVE_VENDORS:
                base_url = self.connector_config.get("base_url")
                if not isinstance(base_url, str) or not base_url.strip():
                    raise ValueError(
                        "connector_config.base_url is required for native platform connectors"
                    )
                if not base_url.strip().startswith(("https://", "http://")):
                    raise ValueError("connector_config.base_url must be an http(s) URL")

            if self.vendor == "datadog":
                if not self.api_secret:
                    raise ValueError(
                        "api_secret is required for Datadog (application key)"
                    )
                unit_prices = self.connector_config.get("unit_prices_usd")
                if not isinstance(unit_prices, dict) or not unit_prices:
                    raise ValueError(
                        "connector_config.unit_prices_usd must be a non-empty object for Datadog pricing"
                    )

            if self.vendor in {"newrelic", "new_relic", "new-relic"}:
                account_id = self.connector_config.get("account_id")
                if not isinstance(account_id, int) and not (
                    isinstance(account_id, str) and account_id.isdigit()
                ):
                    raise ValueError(
                        "connector_config.account_id is required for New Relic (numeric)"
                    )
                nrql_template = self.connector_config.get(
                    "nrql_template"
                ) or self.connector_config.get("nrql_query")
                if not isinstance(nrql_template, str) or not nrql_template.strip():
                    raise ValueError(
                        "connector_config.nrql_template is required for New Relic"
                    )
                unit_prices = self.connector_config.get("unit_prices_usd")
                if not isinstance(unit_prices, dict) or not unit_prices:
                    raise ValueError(
                        "connector_config.unit_prices_usd must be a non-empty object for New Relic pricing"
                    )
        return self


class PlatformConnectionResponse(BaseModel):
    id: UUID
    name: str
    vendor: str
    auth_method: str
    connector_config: dict[str, Any]
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class HybridConnectionCreate(BaseModel):
    """Private/Hybrid infrastructure Cloud+ connection request (feed-based + ledger HTTP pull)."""

    name: str = Field(..., min_length=3, max_length=100, description="Friendly name")
    vendor: str = Field(
        ..., min_length=2, max_length=100, description="Hybrid system/vendor label"
    )
    auth_method: str = Field(
        default="manual", max_length=20, description="manual, csv, or api_key"
    )
    api_key: str | None = Field(
        default=None, max_length=1024, description="API key for native connectors"
    )
    api_secret: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional second secret for native connectors (for example OpenStack app credential secret).",
    )
    connector_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-secret settings (for example ledger HTTP base URL and path).",
    )
    spend_feed: list[dict[str, Any]] = Field(
        default_factory=list, description="Normalized hybrid spend records"
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _normalize_non_empty(value, "name")

    @field_validator("vendor")
    @classmethod
    def _validate_vendor(cls, value: str) -> str:
        return _normalize_non_empty(value, "vendor").lower()

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"manual", "csv", "api_key"}:
            raise ValueError("auth_method must be one of: manual, csv, api_key")
        return normalized

    @model_validator(mode="after")
    def _validate_native_config(self) -> Self:
        if self.auth_method == "api_key" and not self.api_key:
            raise ValueError("api_key is required when auth_method is 'api_key'")

        native_mode = self.auth_method == "api_key"
        if native_mode and self.vendor not in _HYBRID_NATIVE_VENDORS:
            raise ValueError(
                "native Hybrid auth currently supports: ledger_http (and aliases), openstack/cloudkitty, vmware/vcenter. "
                "Use auth_method manual/csv for custom vendors."
            )

        if native_mode:
            if self.vendor in _LEDGER_NATIVE_VENDORS:
                base_url = self.connector_config.get("base_url")
                if not isinstance(base_url, str) or not base_url.strip():
                    raise ValueError(
                        "connector_config.base_url is required for native hybrid connectors"
                    )
                if not base_url.strip().startswith(("https://", "http://")):
                    raise ValueError("connector_config.base_url must be an http(s) URL")

            if self.vendor in {"openstack", "cloudkitty"}:
                if not self.api_secret:
                    raise ValueError(
                        "api_secret is required for OpenStack/CloudKitty (application credential secret)"
                    )
                auth_url = self.connector_config.get("auth_url")
                if not isinstance(auth_url, str) or not auth_url.strip():
                    raise ValueError(
                        "connector_config.auth_url is required for OpenStack Keystone"
                    )
                if not auth_url.strip().startswith(("https://", "http://")):
                    raise ValueError("connector_config.auth_url must be an http(s) URL")
                cloudkitty_url = self.connector_config.get(
                    "cloudkitty_base_url"
                ) or self.connector_config.get("base_url")
                if not isinstance(cloudkitty_url, str) or not cloudkitty_url.strip():
                    raise ValueError(
                        "connector_config.cloudkitty_base_url is required for CloudKitty API"
                    )
                if not cloudkitty_url.strip().startswith(("https://", "http://")):
                    raise ValueError(
                        "connector_config.cloudkitty_base_url must be an http(s) URL"
                    )

            if self.vendor in {"vmware", "vcenter", "vsphere"}:
                if not self.api_secret:
                    raise ValueError(
                        "api_secret is required for VMware/vCenter (password)"
                    )
                base_url = self.connector_config.get("base_url")
                if not isinstance(base_url, str) or not base_url.strip():
                    raise ValueError(
                        "connector_config.base_url is required for VMware/vCenter"
                    )
                if not base_url.strip().startswith(("https://", "http://")):
                    raise ValueError("connector_config.base_url must be an http(s) URL")
                cpu_price = self.connector_config.get("cpu_hour_usd")
                ram_price = self.connector_config.get("ram_gb_hour_usd")
                if not isinstance(cpu_price, (int, float)) or cpu_price <= 0:
                    raise ValueError(
                        "connector_config.cpu_hour_usd must be a positive number for VMware pricing"
                    )
                if not isinstance(ram_price, (int, float)) or ram_price <= 0:
                    raise ValueError(
                        "connector_config.ram_gb_hour_usd must be a positive number for VMware pricing"
                    )
        return self


class HybridConnectionResponse(BaseModel):
    id: UUID
    name: str
    vendor: str
    auth_method: str
    connector_config: dict[str, Any]
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
