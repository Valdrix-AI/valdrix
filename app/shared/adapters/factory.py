"""
Multi-Cloud Adapter Factory - Phase 11: Enterprise Scalability

Standardizes cloud provider interactions and provides a unified interface
for AWS, Azure, and GCP.
"""

from typing import Any
from pydantic import SecretStr
from app.shared.core.credentials import (
    AWSCredentials,
    AzureCredentials,
    GCPCredentials,
    SaaSCredentials,
    LicenseCredentials,
    PlatformCredentials,
    HybridCredentials,
)
from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.adapters.azure import AzureAdapter
from app.shared.adapters.gcp import GCPAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.hybrid import HybridAdapter
from app.shared.adapters.aws_utils import resolve_aws_region_hint
from app.shared.core.exceptions import ConfigurationError
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection


class AdapterFactory:
    @staticmethod
    def get_adapter(connection: Any) -> BaseAdapter:
        """
        Returns the appropriate adapter based on the connection type.
        """
        if isinstance(connection, AWSConnection):
            resolved_region = resolve_aws_region_hint(getattr(connection, "region", ""))

            # Prefer CUR adapter for enterprise accounts if configured
            aws_creds = AWSCredentials(
                account_id=connection.aws_account_id,
                role_arn=connection.role_arn,
                external_id=connection.external_id,
                region=resolved_region,
                cur_bucket_name=connection.cur_bucket_name,
                cur_report_name=connection.cur_report_name,
                cur_prefix=connection.cur_prefix,
            )
            if connection.cur_bucket_name and connection.cur_status == "active":
                return AWSCURAdapter(aws_creds)
            
            raise ConfigurationError(
                "AWS Cost Explorer is not supported in Valdrics. "
                "Cost ingestion requires CUR (Cost and Usage Report) in S3 via Data Exports."
            )

        elif isinstance(connection, AzureConnection):
            azure_creds = AzureCredentials(
                tenant_id=connection.azure_tenant_id,
                client_id=connection.client_id,
                subscription_id=connection.subscription_id,
                client_secret=SecretStr(connection.client_secret) if connection.client_secret else None,
                auth_method=connection.auth_method,
            )
            return AzureAdapter(azure_creds)

        elif isinstance(connection, GCPConnection):
            gcp_creds = GCPCredentials(
                project_id=connection.project_id,
                service_account_json=SecretStr(connection.service_account_json) if connection.service_account_json else None,
                auth_method=connection.auth_method,
                billing_project_id=connection.billing_project_id,
                billing_dataset=connection.billing_dataset,
                billing_table=connection.billing_table,
            )
            return GCPAdapter(gcp_creds)

        elif isinstance(connection, SaaSConnection):
            connector_config = connection.connector_config or {}
            saas_creds = SaaSCredentials(
                platform=connection.vendor,
                api_key=SecretStr(connection.api_key) if connection.api_key else None,
                auth_method=connection.auth_method,
                connector_config=connector_config,
                spend_feed=connection.spend_feed or [],
                extra_config={
                    **connector_config,
                    "auth_method": connection.auth_method,
                    "spend_feed": connection.spend_feed or [],
                },
            )
            return SaaSAdapter(saas_creds)

        elif isinstance(connection, LicenseConnection):
            license_creds = LicenseCredentials(
                vendor=connection.vendor,
                auth_method=connection.auth_method,
                api_key=SecretStr(connection.api_key) if connection.api_key else None,
                connector_config=connection.connector_config or {},
                license_feed=connection.license_feed or [],
            )
            return LicenseAdapter(license_creds)
        elif isinstance(connection, PlatformConnection):
            platform_creds = PlatformCredentials(
                vendor=connection.vendor,
                auth_method=connection.auth_method,
                api_key=SecretStr(connection.api_key) if connection.api_key else None,
                api_secret=SecretStr(connection.api_secret) if connection.api_secret else None,
                connector_config=connection.connector_config or {},
                spend_feed=connection.spend_feed or [],
            )
            return PlatformAdapter(platform_creds)
        elif isinstance(connection, HybridConnection):
            hybrid_creds = HybridCredentials(
                vendor=connection.vendor,
                auth_method=connection.auth_method,
                api_key=SecretStr(connection.api_key) if connection.api_key else None,
                api_secret=SecretStr(connection.api_secret) if connection.api_secret else None,
                connector_config=connection.connector_config or {},
                spend_feed=connection.spend_feed or [],
            )
            return HybridAdapter(hybrid_creds)

        raise ConfigurationError(f"Unsupported connection type or provider: {type(connection)}")
