"""
Multi-Cloud Adapter Factory - Phase 11: Enterprise Scalability

Standardizes cloud provider interactions and provides a unified interface
for AWS, Azure, and GCP.
"""

from typing import Dict, Any
from app.services.adapters.base import BaseAdapter
from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.services.adapters.aws_cur import AWSCURAdapter
from app.services.adapters.azure import AzureAdapter
from app.services.adapters.gcp import GCPAdapter
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection

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

        # Fallback for dynamic types or older code paths
        # This allows passing a mock object or checking by provider property
        provider = getattr(connection, "provider", "").lower()
        if provider == "azure":
            # Assuming connection has necessary fields or casts
            # This path might need to be removed if strictly typed
            return AzureAdapter(connection) 
        elif provider == "gcp":
            return GCPAdapter(connection)
            
        raise ValueError(f"Unsupported connection type or provider: {type(connection)}")
