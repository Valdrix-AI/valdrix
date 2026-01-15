from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

class AWSConnectionCreate(BaseModel):
    """Request body for creating a new AWS connection."""
    aws_account_id: str = Field(..., pattern=r"^\d{12}$", description="12-digit AWS account ID")
    role_arn: str = Field(..., description="Full ARN of the IAM role to assume")
    external_id: str = Field(..., pattern=r"^vx-[a-f0-9]{32}$", description="External ID from setup step")
    region: str = Field(default="us-east-1", description="AWS region for Cost Explorer")
    is_management_account: bool = Field(default=False, description="Whether this is a Management Account for Organizations")
    organization_id: str | None = Field(default=None, description="AWS Organization ID")


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
    created_at: datetime

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
    name: str = Field(..., min_length=3, description="Friendly name for connection")
    azure_tenant_id: str = Field(..., description="Azure Tenant ID (Directory ID)")
    client_id: str = Field(..., description="Application ID")
    subscription_id: str = Field(..., description="Subscription ID")
    client_secret: str | None = Field(default=None, description="Client Secret (Optional for Workload Identity)")
    auth_method: str = Field(default="secret", description="secret or workload_identity")

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
    name: str = Field(..., min_length=3, description="Friendly name")
    project_id: str = Field(..., description="GCP Project ID")
    service_account_json: str | None = Field(default=None, description="Full JSON content (Optional for Workload Identity)")
    auth_method: str = Field(default="secret", description="secret or workload_identity")

class GCPConnectionResponse(BaseModel):
    id: UUID
    name: str
    project_id: str
    is_active: bool
    last_synced_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
