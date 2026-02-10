from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class AWSConnectionCreate(BaseModel):
    """Request body for creating a new AWS connection."""
    aws_account_id: str = Field(..., pattern=r"^\d{12}$", description="12-digit AWS account ID")
    role_arn: str = Field(..., pattern=r"^arn:aws:iam::\d{12}:role/[\w+=,.@-]+$", description="Full ARN of the IAM role to assume")
    external_id: str = Field(..., pattern=r"^vx-[a-f0-9]{32}$", description="External ID from setup step")
    region: str = Field(default="us-east-1", max_length=20, description="AWS region for Cost Explorer")
    is_management_account: bool = Field(default=False, description="Whether this is a Management Account for Organizations")
    organization_id: str | None = Field(default=None, max_length=12, description="AWS Organization ID")


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
    name: str = Field(..., min_length=3, max_length=100, description="Friendly name for connection")
    azure_tenant_id: str = Field(..., max_length=50, description="Azure Tenant ID (Directory ID)")
    client_id: str = Field(..., max_length=50, description="Application ID")
    subscription_id: str = Field(..., max_length=50, description="Subscription ID")
    client_secret: str | None = Field(default=None, max_length=255, description="Client Secret (Optional for Workload Identity)")
    auth_method: str = Field(default="secret", max_length=20, description="secret or workload_identity")

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
    service_account_json: str | None = Field(default=None, max_length=20000, description="Full JSON content (Optional for Workload Identity)")
    auth_method: str = Field(default="secret", max_length=20, description="secret or workload_identity")
    billing_project_id: str | None = Field(default=None, max_length=100, description="Project ID holding BigQuery export")
    billing_dataset: str | None = Field(default=None, max_length=100, description="BigQuery dataset ID")
    billing_table: str | None = Field(default=None, max_length=100, description="BigQuery table ID")

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
