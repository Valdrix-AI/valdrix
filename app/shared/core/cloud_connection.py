"""
Cloud Connection Service - Unified Cloud Account Management

Centralizes:
- Listing connections.
- Verifying connections (delegating to adapters).
- Onboarding templates.
"""

from uuid import UUID
from typing import Dict, Any, List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.shared.adapters.factory import AdapterFactory
from app.shared.core.logging import audit_log

logger = structlog.get_logger()

class CloudConnectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_all_connections(self, tenant_id: UUID) -> Dict[str, List[Any]]:
        """Lists all cloud connections for a tenant, grouped by provider."""
        results = {
            "aws": [],
            "azure": [],
            "gcp": []
        }
        
        # AWS
        aws_q = await self.db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id))
        results["aws"] = aws_q.scalars().all()
        
        # Azure
        azure_q = await self.db.execute(select(AzureConnection).where(AzureConnection.tenant_id == tenant_id))
        results["azure"] = azure_q.scalars().all()
        
        # GCP
        gcp_q = await self.db.execute(select(GCPConnection).where(GCPConnection.tenant_id == tenant_id))
        results["gcp"] = gcp_q.scalars().all()
        
        return results

    async def verify_connection(self, provider: str, connection_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """
        Generic entry point for connection verification.
        Delegates to provider-specific logic while maintaining a common interface.
        """
        model_map = {
            "aws": AWSConnection,
            "azure": AzureConnection,
            "gcp": GCPConnection
        }
        
        model = model_map.get(provider.lower())
        if not model:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
            
        result = await self.db.execute(
            select(model).where(
                model.id == connection_id,
                model.tenant_id == tenant_id
            )
        )
        connection = result.scalar_one_or_none()
        
        if not connection:
            raise HTTPException(status_code=404, detail="Connection not found")

        try:
            adapter = AdapterFactory.get_adapter(connection)
            is_valid = await adapter.verify_connection()
            
            from datetime import datetime, timezone
            if is_valid:
                # Update status based on model fields (most have status or is_active)
                if hasattr(connection, "status"):
                    connection.status = "active"
                if hasattr(connection, "is_active"):
                    connection.is_active = True
                    
                if hasattr(connection, "last_verified_at"):
                    connection.last_verified_at = datetime.now(timezone.utc)
                if hasattr(connection, "last_synced_at"):
                    connection.last_synced_at = datetime.now(timezone.utc)
                
                if hasattr(connection, "error_message"):
                    connection.error_message = None
                    
                await self.db.commit()
                audit_log(f"{provider}_connection_verified", "system", str(tenant_id), {"id": str(connection_id)})
                
                return {
                    "status": "active",
                    "provider": provider,
                    "account_id": getattr(connection, "aws_account_id", 
                                  getattr(connection, "subscription_id", 
                                  getattr(connection, "project_id", None)))
                }
            else:
                if hasattr(connection, "status"):
                    connection.status = "error"
                if hasattr(connection, "is_active"):
                    connection.is_active = False
                await self.db.commit()
                raise HTTPException(status_code=400, detail=f"{provider.upper()} verification failed")
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error("provider_verification_failed", provider=provider, error=str(e), connection_id=str(connection_id))
            if hasattr(connection, "status"):
                connection.status = "error"
                connection.error_message = str(e)
            await self.db.commit()
            raise HTTPException(status_code=500, detail=str(e))

    @staticmethod
    def get_aws_setup_templates(external_id: str) -> Dict[str, str]:
        """AWS specific onboarding templates."""
        return {
            "magic_link": f"https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?stackName=ValdrixAccess&templateURL=https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml&param_ExternalId={external_id}",
            "cfn_template": "https://valdrix-public.s3.amazonaws.com/templates/aws-access.yaml",
            "terraform_snippet": (
                "resource \"aws_iam_role\" \"valdrix_access\" {\n"
                "  name = \"ValdrixAccessRole\"\n"
                f"  assume_role_policy = jsonencode({{... external_id = \"{external_id}\" ...}})\n"
                "}"
            )
        }
