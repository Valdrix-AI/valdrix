"""
Typed Credential Classes 
Standardizes cloud provider credentials into O(1) Pydantic models.
This decouples adapters from SQLAlchemy models and ensures strict type safety.
"""
from pydantic import BaseModel, Field, SecretStr
from typing import Optional, Dict, Any

class CloudCredentials(BaseModel):
    """Base class for all cloud credentials."""
    pass

class AWSCredentials(CloudCredentials):
    """AWS STS AssumeRole Credentials."""
    account_id: str = Field(..., min_length=12, max_length=12)
    role_arn: str
    external_id: str
    region: str = "us-east-1"
    tenant_id: Optional[Any] = None  # UUID of the tenant
    
    @property
    def aws_account_id(self) -> str:
        return self.account_id
    
    # CUR Specifics
    cur_bucket_name: Optional[str] = None
    cur_report_name: Optional[str] = None
    cur_prefix: Optional[str] = None

class AzureCredentials(CloudCredentials):
    """Azure Service Principal Credentials."""
    tenant_id: str
    client_id: str
    subscription_id: str
    client_secret: Optional[SecretStr] = None
    auth_method: str = "secret"  # secret | workload_identity

class GCPCredentials(CloudCredentials):
    """GCP Service Account or Workload Identity."""
    project_id: str
    service_account_json: Optional[SecretStr] = None
    auth_method: str = "secret"  # secret | workload_identity
    
    # BigQuery Billing Template
    billing_project_id: Optional[str] = None
    billing_dataset: Optional[str] = None
    billing_table: Optional[str] = None

class SaaSCredentials(CloudCredentials):
    """Generic SaaS API Credentials."""
    platform: str
    api_key: Optional[SecretStr] = None
    auth_method: str = "manual"
    connector_config: Dict[str, Any] = Field(default_factory=dict)
    spend_feed: list[dict[str, Any]] = Field(default_factory=list)
    base_url: Optional[str] = None
    extra_config: Dict[str, Any] = Field(default_factory=dict)

class LicenseCredentials(CloudCredentials):
    """ITAM/License vendor credentials."""
    vendor: str
    auth_method: str = "manual"
    api_key: Optional[SecretStr] = None
    connector_config: Dict[str, Any] = Field(default_factory=dict)
    license_feed: list[dict[str, Any]] = Field(default_factory=list)

class PlatformCredentials(CloudCredentials):
    """Internal Platform/Shared Services credentials."""
    vendor: str
    auth_method: str = "manual"
    api_key: Optional[SecretStr] = None
    api_secret: Optional[SecretStr] = None
    connector_config: Dict[str, Any] = Field(default_factory=dict)
    spend_feed: list[dict[str, Any]] = Field(default_factory=list)

class HybridCredentials(CloudCredentials):
    """Hybrid/Private cloud credentials."""
    vendor: str
    auth_method: str = "manual"
    api_key: Optional[SecretStr] = None
    api_secret: Optional[SecretStr] = None
    connector_config: Dict[str, Any] = Field(default_factory=dict)
    spend_feed: list[dict[str, Any]] = Field(default_factory=list)
