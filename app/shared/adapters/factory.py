"""
Multi-Cloud Adapter Factory - Phase 11: Enterprise Scalability

Standardizes cloud provider interactions and provides a unified interface
for AWS, Azure, and GCP.
"""

from typing import Any
from app.shared.adapters.base import BaseAdapter
from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.aws_cur import AWSCURAdapter
from app.shared.adapters.azure import AzureAdapter
from app.shared.adapters.gcp import GCPAdapter
from app.shared.adapters.saas import SaaSAdapter
from app.shared.adapters.license import LicenseAdapter
from app.shared.adapters.platform import PlatformAdapter
from app.shared.adapters.hybrid import HybridAdapter
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
            # Prefer CUR adapter for enterprise accounts if configured
            if connection.cur_bucket_name and connection.cur_status == "active":
                return AWSCURAdapter(connection)
            return MultiTenantAWSAdapter(connection)

        elif isinstance(connection, AzureConnection):
            return AzureAdapter(connection)

        elif isinstance(connection, GCPConnection):
            return GCPAdapter(connection)
        elif isinstance(connection, SaaSConnection):
            return SaaSAdapter(connection)
        elif isinstance(connection, LicenseConnection):
            return LicenseAdapter(connection)
        elif isinstance(connection, PlatformConnection):
            return PlatformAdapter(connection)
        elif isinstance(connection, HybridConnection):
            return HybridAdapter(connection)

        # Fallback for dynamic types/mocks: route by `provider` attribute.
        provider = getattr(connection, "provider", "").lower()
        if provider == "azure":
            # Assuming connection has necessary fields or casts
            # This path might need to be removed if strictly typed
            return AzureAdapter(connection)
        elif provider == "gcp":
            return GCPAdapter(connection)
        elif provider == "saas":
            return SaaSAdapter(connection)
        elif provider == "license":
            return LicenseAdapter(connection)
        elif provider == "platform":
            return PlatformAdapter(connection)
        elif provider == "hybrid":
            return HybridAdapter(connection)

        raise ValueError(f"Unsupported connection type or provider: {type(connection)}")
